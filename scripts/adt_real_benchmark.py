"""Run a reproducible, research-only ADT_STR vs DSP benchmark.

This script actually loads a pinned, locally installed upstream ADT_STR source
tree and a pinned official Hub model checkpoint. Network download is explicitly
limited to one HF variant. No third-party weights are redistributed.
Reference WAV is synthetic; reported F1 is NOT real-world performance.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
import traceback
from pathlib import Path

import pretty_midi

from midivolt.adt_hf_probe import REPO_ID, VARIANT, probe_model
from midivolt.compare_drums import compare
from midivolt.drums import transcribe_drum_wav


def sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def generate_fixture(wav: Path, midi: Path) -> None:
    # The generator is maintained in MIDIVOLT's test suite, not third-party data.
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "tests" / "transcription"))
    from test_drums import PATTERN, PITCH, synthetic_drums

    synthetic_drums(wav)
    reference = pretty_midi.PrettyMIDI(initial_tempo=138)
    track = pretty_midi.Instrument(program=0, is_drum=True, name="synthetic_truth")
    for kind, start in PATTERN:
        track.notes.append(pretty_midi.Note(
            pitch=PITCH[kind], velocity=100, start=start, end=start + 0.1
        ))
    reference.instruments.append(track)
    reference.write(str(midi))


def run_benchmark(
    *,
    upstream_root: Path,
    model_revision: str,
    upstream_revision: str,
    output: Path,
) -> dict:
    import numpy as np
    import torch
    from huggingface_hub import snapshot_download
    from scipy.io import wavfile

    root = Path(upstream_root).resolve()
    if not (root / "adt_transcriber.py").is_file():
        raise ValueError("Trusted upstream source root must contain adt_transcriber.py")
    if len(upstream_revision) != 40:
        raise ValueError("Pin an exact upstream source revision.")
    result_sha = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True, timeout=15,
    ).stdout.strip()
    if result_sha != upstream_revision:
        raise RuntimeError("Upstream source SHA mismatch: " + result_sha)

    output.mkdir(parents=True, exist_ok=True)
    wav, reference_path = output / "synthetic_drums.wav", output / "truth.mid"
    generate_fixture(wav, reference_path)
    reference = pretty_midi.PrettyMIDI(str(reference_path))

    # Stage 1: rights/provenance and artifact identity.
    model_info = probe_model(model_revision)
    if model_info["missing_files"]:
        raise RuntimeError("Pinned model is missing required ADT_STR config/weights.")
    (output / "hub_provenance.json").write_text(
        json.dumps(model_info, indent=2) + "\n", encoding="utf-8"
    )
    download_started = time.perf_counter()
    local_model_root = Path(snapshot_download(
        repo_id=REPO_ID,
        revision=model_revision,
        allow_patterns=[f"{VARIANT}/*"],
    ))
    download_seconds = time.perf_counter() - download_started
    variant_dir = local_model_root / VARIANT
    weight = variant_dir / "model.safetensors"
    config = variant_dir / "adt_config.yaml"
    if not weight.is_file() or not config.is_file():
        raise RuntimeError("Hub checkpoint/config missing after download.")
    # The checkpoint is used locally and never copied into uploaded artifacts.
    hashes = {weight.name: sha256(weight), config.name: sha256(config)}

    # Stage 2: fair baseline on the same drum WAV and reference.
    start_dsp = time.perf_counter()
    dsp, dsp_details = transcribe_drum_wav(wav, tempo=138)
    dsp_seconds = time.perf_counter() - start_dsp
    dsp.write(str(output / "dsp.mid"))

    # Stage 3: actual upstream HF model inference, including load timing.
    sys.path.insert(0, str(root))
    from adt_transcriber import ADTTranscriber
    model_started = time.perf_counter()
    transcriber = ADTTranscriber.from_pretrained(
        str(local_model_root), variant=VARIANT, device="cpu"
    )
    load_seconds = time.perf_counter() - model_started

    sample_rate, raw = wavfile.read(wav)
    if raw.dtype != np.int16:
        raise RuntimeError("Unexpected synthetic PCM type.")
    waveform = torch.as_tensor(raw.astype(np.float32) / 32768.0)
    inf_started = time.perf_counter()
    predicted_path = transcriber.transcribe(
        waveform, sample_rate=sample_rate, output_dir=str(output),
        batch_size=1, max_length=384
    )
    infer_seconds = time.perf_counter() - inf_started
    actual = pretty_midi.PrettyMIDI(str(predicted_path))
    if not actual.instruments or any(not ins.is_drum for ins in actual.instruments):
        raise RuntimeError("ADT_STR returned no drum-flagged MIDI track.")
    actual.write(str(output / "adt_str.mid"))

    measurements = compare(reference, dsp, actual)
    duration_seconds = len(raw) / sample_rate
    report = {
        "status": "completed_research_only",
        "source": {
            "type": "self_generated_synthetic_drums",
            "duration_seconds": duration_seconds,
            "reference_wav_sha256": sha256(wav),
            "reference_midi_sha256": sha256(reference_path),
            "warning": "Synthetic 2.8-second fixture. NOT human playing, no generalizable F1.",
        },
        "model": {
            "repo_id": REPO_ID,
            "hub_revision": model_revision,
            "variant": VARIANT,
            "source_git_revision": result_sha,
            "weights_and_config_sha256": hashes,
            "license_status": "research_only_pending_commercial_due_diligence",
        },
        "performance": {
            "cpu": platform.processor(),
            "platform": platform.platform(),
            "python": platform.python_version(),
            "torch": torch.__version__,
            "drum_duration_seconds": duration_seconds,
            "model_download_seconds_excluded": round(download_seconds, 3),
            "dsp_seconds": round(dsp_seconds, 3),
            "adt_model_load_seconds": round(load_seconds, 3),
            "adt_inference_seconds": round(infer_seconds, 3),
            "adt_cold_total_seconds_excluding_download": round(load_seconds + infer_seconds, 3),
            "dsp_realtime_factor": round(dsp_seconds / duration_seconds, 3),
            "adt_inference_realtime_factor": round(infer_seconds / duration_seconds, 3),
        },
        "dsp_diagnostics": dsp_details,
        "comparison": measurements,
    }
    (output / "benchmark.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream-root", type=Path, required=True)
    parser.add_argument("--model-revision", required=True)
    parser.add_argument("--upstream-revision", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--research-only", action="store_true", required=True)
    args = parser.parse_args(argv)
    if not args.research_only:
        parser.exit(2, "ADT_STR model execution requires --research-only\n")
    args.output.mkdir(parents=True, exist_ok=True)
    try:
        result = run_benchmark(
            upstream_root=args.upstream_root,
            model_revision=args.model_revision,
            upstream_revision=args.upstream_revision,
            output=args.output,
        )
    except Exception as exc:
        result = {
            "status": "failed",
            "message": str(exc),
            "traceback_tail": traceback.format_exc()[-3000:],
            "research_only": True,
        }
        (args.output / "benchmark_error.json").write_text(
            json.dumps(result, indent=2) + "\n", encoding="utf-8"
        )
        print(json.dumps(result, indent=2), file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
