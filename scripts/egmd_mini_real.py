"""One-off actual E-GMD MIDI/WAV research benchmark without a 90-GB download.

Official CC-BY-4.0 release; real human drumming replayed through an electronic
Roland TD-17 kit. Results are electronic-kit, NOT direct acoustic microphone
recording scores. No training or model fine-tuning occurs. WAV/MIDI/model weights
must not be included in publicly uploaded CI artifacts.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import os
import platform
import sys
import time
import traceback
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pretty_midi
from scipy.io import wavfile

from midivolt.egmd_import import read_metadata
from midivolt.egmd_selection import select_mixed_test_rows, selection_summary
from midivolt.drums import transcribe_drum_wav
from midivolt.drum_suite import _normalize_reference, _summarize
from midivolt.compare_drums import evaluate_drums
from midivolt.alignment_qc import inspect_alignment

CSV_URL = "https://storage.googleapis.com/magentadata/datasets/e-gmd/v1.0.0/e-gmd-v1.0.0.csv"
ZIP_URL = "https://storage.googleapis.com/magentadata/datasets/e-gmd/v1.0.0/e-gmd-v1.0.0.zip"
ZIP_FULL_SHA256 = "7d9a264fb4c9eabd9fec09d5f8e333192f529b1a1b845d170279a977ac436053"
MODEL_REVISION = "a33c5c6b191a4ca1e0f6dc22140947485eb36ce8"
SOURCE_REVISION = "77dbef225e7029478ebfb916f20c7a00274f0f12"
MODEL_SHA256 = "f94d1773d929166e0a3f63d305975aa6667512f8a71d7706872e1f8b23ca930b"
HF_ID = "Pierfrancesco/adt-str"
VARIANT = "setting-tau-0.8"


def digest_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def get_small_csv(dest: Path) -> tuple[Path, str]:
    import requests  # Optional network dependency; not needed by unit tests.
    response = requests.get(CSV_URL, timeout=30, stream=True)
    response.raise_for_status()
    data = bytearray()
    try:
        for block in response.iter_content(65536):
            data.extend(block)
            if len(data) > 10 * 1024 * 1024:
                raise RuntimeError("Aborting unexpected >10MB official metadata response")
    finally:
        response.close()
    if not data.startswith(b"drummer,") and not data.startswith(b"\xef\xbb\xbfdrummer,"):
        raise RuntimeError("Official metadata CSV header not recognized")
    dest.write_bytes(data)
    return dest, digest_file(dest)


def preflight_ranges(url: str) -> int:
    """Refuse byte-range-ignoring hosts before touching a 90GB archive."""
    import requests
    response = requests.get(
        url, headers={"Range": "bytes=0-0"}, stream=True, timeout=30
    )
    try:
        length = response.headers.get("Content-Range", "")
        if response.status_code != 206 or not length.startswith("bytes 0-0/"):
            raise RuntimeError(
                "E-GMD ZIP does not support HTTP Range; refusing full-archive download "
                f"(status={response.status_code}, content-range={length!r})"
            )
        return int(length.split("/")[-1])
    finally:
        response.close()


def _find_member(members: list[str], target: str) -> str:
    path = target.strip("/")
    matches = [name for name in members if name == path or name.endswith("/" + path)]
    if len(matches) != 1:
        raise RuntimeError(f"Expected exactly one ZIP entry for {target!r}, found {len(matches)}")
    return matches[0]


def acquire_selected(zip_url: str, rows: list[dict], base: Path, *, max_entry_mb: int = 28) -> list[dict]:
    from remotezip import RemoteZip

    base.mkdir(parents=True, exist_ok=True)
    # Never construct output paths directly from the remote archive entry.
    records = []
    with RemoteZip(zip_url) as archive:
        members = archive.infolist()
        names = [x.filename for x in members]
        index = {item.filename: item for item in members}
        for number, row in enumerate(rows):
            fields = {"wav": row["audio_filename"], "midi": row["midi_filename"]}
            local = {}
            for kind, relative in fields.items():
                member = _find_member(names, relative)
                info = index[member]
                if info.file_size > max_entry_mb * (1 << 20):
                    raise RuntimeError(f"E-GMD selected {kind} member exceeds {max_entry_mb} MiB")
                suffix = ".wav" if kind == "wav" else ".mid"
                target = base / f"recording_{number:02d}{suffix}"
                data = archive.read(member)
                if len(data) != info.file_size:
                    raise RuntimeError(f"E-GMD member decompressed length mismatch: {member}")
                target.write_bytes(data)
                local[kind] = str(target)
            records.append({
                "source_song_id": row["id"],
                "source_split": row["split"],
                "style": row["style"],
                "drummer": row["drummer"],
                "beat_type": row["beat_type"],
                "bpm": float(row["bpm"]),
                "duration_metadata_seconds": float(row["duration"]),
                "kit_name": row["kit_name"],
                "wav": local["wav"],
                "midi": local["midi"],
                "wav_sha256": digest_file(Path(local["wav"])),
                "midi_sha256": digest_file(Path(local["midi"])),
                "official_wav_member": row["audio_filename"],
                "official_midi_member": row["midi_filename"],
            })
    return records


def _float_pcm(raw: np.ndarray) -> np.ndarray:
    # Convert to mono without discarding integer PCM scaling information.
    dtype = raw.dtype
    if raw.ndim == 2:
        raw = raw.mean(axis=1, dtype=np.float32)
    if dtype == np.uint8:
        return (raw.astype(np.float32) - 128.0) / 128.0
    if np.issubdtype(dtype, np.integer):
        return raw.astype(np.float32) / (2.0 ** (8 * dtype.itemsize - 1))
    if np.issubdtype(dtype, np.floating):
        return raw.astype(np.float32)
    raise ValueError("Unsupported PCM dtype: " + str(raw.dtype))


def evaluate_wavs(files: list[dict], output: Path, *, adt_root: Path, model_revision: str) -> dict:
    import torch
    from huggingface_hub import hf_hub_download
    from adt_transcriber import ADTTranscriber

    if model_revision != MODEL_REVISION:
        raise ValueError("Unreviewed model version")
    # Reuse one checkpoint across all songs.
    local = {}
    for filename in ("model.safetensors", "adt_config.yaml", "config.json"):
        local[filename] = Path(hf_hub_download(
            repo_id=HF_ID, revision=MODEL_REVISION,
            filename=f"{VARIANT}/{filename}",
        ))
    if digest_file(local["model.safetensors"]) != MODEL_SHA256:
        raise RuntimeError("Downloaded weight SHA-256 mismatch")
    loaded = time.perf_counter()
    model = ADTTranscriber.from_pretrained(
        str(local["model.safetensors"].parent.parent),
        variant=VARIANT, device="cpu",
    )
    model_load_seconds = time.perf_counter() - loaded
    measurements = []
    for index, file in enumerate(files):
        wav = Path(file["wav"])
        truth_file = Path(file["midi"])
        truth = _normalize_reference(pretty_midi.PrettyMIDI(str(truth_file)), "roland_td11_to_gm")
        # Discard clips with zero validated reference drum notes, count as failure.
        if not sum(len(ins.notes) for ins in truth.instruments):
            raise RuntimeError(f"No ground truth drum events for {file['source_song_id']}")
        info = {"source_song_id": file["source_song_id"],
                "audio_domain": "electronic_kit_recording",
                "style": file["style"], "kit_name": file["kit_name"],
                "audio_sha256": file["wav_sha256"],
                "midi_sha256": file["midi_sha256"],
                "alignment_qc": inspect_alignment(wav, truth)}
        sr, pcm = wavfile.read(str(wav))
        wave_tensor = torch.as_tensor(_float_pcm(pcm))
        duration = len(wave_tensor) / sr
        for engine in ("dsp", "adt_str"):
            started = time.perf_counter()
            try:
                if engine == "dsp":
                    prediction, _ = transcribe_drum_wav(wav, tempo=file["bpm"])
                else:
                    subfolder = output / f"adt_output_{index:02d}"
                    subfolder.mkdir(exist_ok=True)
                    predicted_path = model.transcribe(
                        wave_tensor, sample_rate=sr, output_dir=str(subfolder),
                        batch_size=1, max_length=384,
                    )
                    prediction = pretty_midi.PrettyMIDI(str(predicted_path))
                scores = evaluate_drums(truth, prediction)
                failed = False
                reason = None
            except Exception as exc:
                failed = True
                reason = f"{type(exc).__name__}: {str(exc)[:200]}"
                fallback = pretty_midi.PrettyMIDI()
                fallback.instruments.append(pretty_midi.Instrument(program=0, is_drum=True))
                scores = evaluate_drums(truth, fallback)
            seconds = time.perf_counter() - started
            measurements.append({
                "sample_id": f"egmd_{index}",
                "song_id": file["source_song_id"],
                "engine": engine,
                "audio_domain": "electronic_kit_recording",
                "seconds": round(seconds, 4),
                "realtime_factor": round(seconds / duration, 5),
                "duration_seconds": duration,
                "failed": failed,
                "error": reason,
                "scores": scores,
                "kit_name": file["kit_name"],
                "style": file["style"],
                "alignment_quality": info["alignment_qc"],
            })
    grouped = {
        engine: _summarize([item for item in measurements if item["engine"] == engine])
        for engine in ("dsp", "adt_str")
    }
    return {
        "status": "research_only_completed",
        "dataset": "E-GMD v1.0.0",
        "dataset_type": "human_performed_electronic_drumkit_audio_NOT_direct_acoustic_drums",
        "data_license": "Google LLC CC BY 4.0, source attribution required",
        "full_archive_sha256_from_upstream": ZIP_FULL_SHA256,
        "model": {"id": HF_ID, "revision": MODEL_REVISION, "variant": VARIANT,
                  "sha256": MODEL_SHA256, "commercial_status": "not_cleared"},
        "runtime": {"python": platform.python_version(), "torch":torch.__version__,
                    "platform":platform.platform(), "model_load_seconds": round(model_load_seconds, 3)},
        "sample_provenance": [
            {k:v for k,v in file.items() if k not in ("wav","midi")}
            for file in files
        ],
        "performance_by_engine": grouped,
        "samples": measurements,
        "caveats": [
            "This is a small one-off test subset selected from the official held-out TEST split.",
            "Full archive SHA-256 is upstream declared, not rehashed locally (no 90GB transfer).",
            "Each range-extracted ZIP member has its own locally computed SHA-256.",
            "No data, checkpoint or notes used for training/fine-tuning.",
            "Acoustic room microphone results cannot be inferred from electronic drumkit renderings.",
            "Research-only: model-license commercial review remains open.",
        ],
    }


def run(args) -> int:
    # Prevent the default model benchmark running without explicit research opt-in.
    if not args.research_only:
        raise RuntimeError("Explicit --research-only is required.")
    if args.max_samples < 1 or args.max_samples > 24:
        raise RuntimeError("--max-samples must be 1..24")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    csvpath, csvhash = get_small_csv(output / "metadata.csv")
    rows = read_metadata(csvpath)
    selection = select_mixed_test_rows(
        rows, count=args.max_samples,
        short_fill_count=args.short_fills,
        min_long_duration=args.min_duration,
        max_long_duration=args.max_duration,
        min_drummers=args.min_drummers, kit=args.kit,
    )
    plan = {
        "dataset": "E-GMD v1.0.0",
        "metadata_url": CSV_URL, "metadata_sha256": csvhash,
        "archive_url": ZIP_URL, "declared_full_archive_sha256": ZIP_FULL_SHA256,
        "sampling_summary": selection_summary(selection),
        "selection_strata": {
            "long_grooves": args.max_samples - args.short_fills,
            "short_fills": args.short_fills,
            "long_duration_seconds": [args.min_duration, args.max_duration],
            "short_fill_duration_seconds": [1.0, 7.0],
        },
        "selected": [{k: row[k] for k in (
            "id","drummer","split","style","beat_type","bpm","duration","kit_name",
            "audio_filename","midi_filename"
        )} for row in selection],
        "license": "CC-BY-4.0 / research only MIDIVOLT model",
    }
    (output / "selection_plan.json").write_text(json.dumps(plan, indent=2) + "\n")
    if args.plan_only:
        print(json.dumps({
            "status": "selection_plan_only",
            "sampling_summary": plan["sampling_summary"],
            "selected": plan["selected"],
            "metadata_sha256": csvhash,
        }, indent=2, ensure_ascii=False))
        return 0
    file_size = preflight_ranges(ZIP_URL)
    plan["remote_zip_size_bytes"] = file_size
    files = acquire_selected(ZIP_URL, selection, output / "private_pairs", max_entry_mb=args.max_entry_mb)
    if len(files) != len(selection):
        raise RuntimeError("Missing pair despite successful preflight.")
    (output / "selection_plan.json").write_text(json.dumps(plan, indent=2) + "\n")
    if args.fetch_only:
        data = {"status":"success_fetch_only","pairs":len(files),
                "wav_and_midi_sha256":[{"song_id":r["source_song_id"],
                                        "wav_sha256":r["wav_sha256"],"midi_sha256":r["midi_sha256"]}
                                       for r in files]}
    else:
        if not args.upstream_root:
            raise RuntimeError("Must supply pinned upstream ADT_STR checkout")
        import subprocess
        checkout = subprocess.run(
            ["git","-C",str(args.upstream_root),"rev-parse","HEAD"],
            capture_output=True,text=True,check=True,timeout=15
        ).stdout.strip()
        if checkout != SOURCE_REVISION:
            raise RuntimeError("ADT_STR upstream source revision not pinned as expected")
        sys.path.insert(0,str(args.upstream_root))
        data = evaluate_wavs(files, output, adt_root=args.upstream_root, model_revision=MODEL_REVISION)
        data["selection_plan_sha256"] = digest_file(output / "selection_plan.json")
    (output / "research_metrics.json").write_text(json.dumps(data,indent=2,ensure_ascii=False)+"\n")
    print(json.dumps(data,indent=2,ensure_ascii=False))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output",type=Path,required=True)
    ap.add_argument("--upstream-root",type=Path)
    ap.add_argument("--max-samples",type=int,default=6)
    ap.add_argument("--min-duration",type=float,default=8.0)
    ap.add_argument("--max-duration",type=float,default=35.0)
    ap.add_argument("--min-drummers",type=int,default=3)
    ap.add_argument("--short-fills",type=int,default=2)
    ap.add_argument("--kit",default="Acoustic Kit")
    ap.add_argument("--plan-only",action="store_true",
                    help="Metadata-only preview, no ZIP access or model weights")
    ap.add_argument("--max-entry-mb",type=int,default=28)
    ap.add_argument("--fetch-only",action="store_true")
    ap.add_argument("--research-only",action="store_true")
    args = ap.parse_args(argv)
    try:
        return run(args)
    except Exception as exc:
        args.output.mkdir(parents=True,exist_ok=True)
        problem={"status":"failed","reason":str(exc),"traceback_tail":traceback.format_exc()[-2400:]}
        (args.output/"research_error.json").write_text(json.dumps(problem,indent=2)+"\n")
        print(json.dumps(problem,indent=2),file=sys.stderr)
        return 1


if __name__=="__main__":
    raise SystemExit(main())
