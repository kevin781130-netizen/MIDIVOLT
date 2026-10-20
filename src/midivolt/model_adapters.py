"""Offline model-process integration; no weights downloaded or vendored."""
from __future__ import annotations
from copy import deepcopy
from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import subprocess
import tempfile

import pretty_midi
from .io import read_midi, write_midi
from .review_engine import create_proposal

@dataclass(frozen=True)
class GenerationReport:
    model: str
    candidate: Path
    tracks: int
    notes: int
    source: Path | None
    manifest: Path | None
    locked: tuple[int, ...]
    warnings: tuple[str, ...]

    def as_dict(self):
        return {
            "model": self.model, "candidate": str(self.candidate),
            "tracks": self.tracks, "notes": self.notes,
            "source": str(self.source) if self.source else None,
            "manifest": str(self.manifest) if self.manifest else None,
            "locked_tracks": list(self.locked), "warnings": list(self.warnings),
        }

def _runner_script(model):
    return Path(__file__).parent / "model_runners" / (model + "_runner.py")

def _file(value, label):
    p = Path(value).expanduser().resolve(strict=True)
    if not p.is_file():
        raise ValueError(f"{label} must be a file: {p}")
    return p

def _dir(value, label):
    p = Path(value).expanduser().resolve(strict=True)
    if not p.is_dir():
        raise ValueError(f"{label} must be a directory: {p}")
    return p

def append_generated_tracks(source: pretty_midi.PrettyMIDI,
                            generated: pretty_midi.PrettyMIDI) -> pretty_midi.PrettyMIDI:
    """Append model notes using quarter-note alignment; keep source tracks/maps untouched."""
    result = deepcopy(source)
    def translate(seconds):
        tick = generated.time_to_tick(float(seconds))
        return float(source.tick_to_time(round(tick * source.resolution / generated.resolution)))
    for instrument in generated.instruments:
        if not instrument.notes:
            continue
        track = deepcopy(instrument)
        track.name = "MIDIVOLT AI | " + (instrument.name or
            pretty_midi.program_to_instrument_name(instrument.program))
        for note in track.notes:
            note.start, note.end = translate(note.start), translate(note.end)
            if note.end <= note.start:
                raise ValueError("Model note has invalid duration after alignment")
        for cc in track.control_changes:
            cc.time = translate(cc.time)
        for bend in track.pitch_bends:
            bend.time = translate(bend.time)
        result.instruments.append(track)
    if len(result.instruments) == len(source.instruments):
        raise ValueError("Model returned no notes to append")
    return result

def generate_candidate(*, model, python_executable, checkout, checkpoint,
                       output_path, source_path=None, manifest_path=None,
                       locked_tracks=None, prompt=None, vocab_path=None,
                       t5_dir=None, melody_program=None, seconds=None,
                       top_p=0.98, temperature=0.9, max_tokens=2000,
                       timeout=1200.0, seed=None):
    """Run a separately installed model, produce MIDI, and optionally a guarded proposal."""
    if model not in ("text2midi", "anticipation"):
        raise ValueError("Unsupported model")
    if not math.isfinite(timeout) or not 1 <= timeout <= 7200:
        raise ValueError("--timeout must be 1..7200 seconds")
    if seed is not None and (type(seed) is not int or not 0 <= seed < 2**31):
        raise ValueError("--seed must be a nonnegative 31-bit integer")
    exe = _file(python_executable, "Model Python interpreter")
    root = _dir(checkout, "Upstream model checkout")
    if model == "text2midi":
        if not (root / "model" / "transformer_model.py").is_file():
            raise ValueError("Missing Text2midi model/transformer_model.py")
        if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 8192:
            raise ValueError("Text2midi requires --prompt (1..8192 chars)")
        if vocab_path is None or t5_dir is None:
            raise ValueError("Text2midi requires --vocab and local --t5-dir")
        vocab = _file(vocab_path, "Tokenizer vocabulary")
        t5 = _dir(t5_dir, "T5 tokenizer cache directory")
        checkpoint = _file(checkpoint, "Text2midi checkpoint")
        if not math.isfinite(temperature) or not 0.1 <= temperature <= 2:
            raise ValueError("--temperature must be 0.1..2")
        if type(max_tokens) is not int or not 32 <= max_tokens <= 4096:
            raise ValueError("--max-tokens must be 32..4096")
    else:
        if not (root / "anticipation" / "sample.py").is_file():
            raise ValueError("Missing anticipation/sample.py")
        if source_path is None:
            raise ValueError("Anticipation requires --source")
        if type(melody_program) is not int or not 0 <= melody_program <= 127:
            raise ValueError("Anticipation requires --melody-program 0..127")
        if seconds is None or not math.isfinite(seconds) or not 0.5 <= seconds <= 120:
            raise ValueError("--seconds must be 0.5..120")
        if not math.isfinite(top_p) or not 0 < top_p <= 1:
            raise ValueError("--top-p must be (0,1]")
        checkpoint = _dir(checkpoint, "Anticipation model directory")
    src = _file(source_path, "Source MIDI") if source_path is not None else None
    dst = Path(output_path).expanduser().resolve()
    manifest = Path(manifest_path).expanduser().resolve() if manifest_path else None
    locked = list(locked_tracks or [])
    if not dst.parent.is_dir() or dst.suffix.lower() not in (".mid", ".midi"):
        raise ValueError("Candidate must be a .mid/.midi in an existing directory")
    if manifest and (src is None or not locked):
        raise ValueError("--manifest requires --source and --lock")
    if locked and (src is None or manifest is None):
        raise ValueError("--lock requires --source and --manifest")
    paths = [v for v in (src, dst, manifest) if v is not None]
    if len(set(paths)) != len(paths):
        raise ValueError("Input, candidate and manifest must differ")
    if any(p.exists() for p in (dst, manifest) if p is not None):
        raise FileExistsError("Output MIDI or manifest already exists")
    if manifest and (manifest.suffix.lower() != ".json" or not manifest.parent.is_dir()):
        raise ValueError("Manifest must be a new JSON file in an existing directory")
    source_midi = read_midi(src) if src else None
    if manifest and (len(set(locked)) != len(locked) or any(
            type(i) is not int or i < 0 or i >= len(source_midi.instruments)
            for i in locked)):
        raise ValueError("Lock indexes must exist and be unique")
    runner = _runner_script(model)
    if not runner.is_file():
        raise FileNotFoundError(runner)
    with tempfile.TemporaryDirectory(prefix="midivolt-inference-") as td:
        raw = Path(td) / "raw.mid"
        args = [str(exe), str(runner), "--checkout", str(root),
                "--checkpoint", str(checkpoint), "--out", str(raw)]
        if seed is not None:
            args += ["--seed", str(seed)]
        if model == "text2midi":
            args += ["--prompt", prompt, "--vocab", str(vocab),
                     "--t5-dir", str(t5), "--temperature", str(temperature),
                     "--max-tokens", str(max_tokens)]
        else:
            args += ["--source", str(src), "--melody-program", str(melody_program),
                     "--seconds", str(seconds), "--top-p", str(top_p)]
        env = os.environ.copy()
        env.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1",
                   HF_DATASETS_OFFLINE="1", TOKENIZERS_PARALLELISM="false")
        try:
            task = subprocess.run(args, cwd=root, env=env, shell=False,
                                  capture_output=True, text=True, errors="replace",
                                  timeout=timeout, check=False)
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"{model} inference timed out") from exc
        if task.returncode:
            diagnostic = (task.stderr or task.stdout or "no details")[-2000:]
            raise RuntimeError(f"{model} inference failed: {diagnostic}")
        if not raw.is_file():
            raise RuntimeError("Model produced no MIDI file")
        generated = read_midi(raw)
        if not any(inst.notes for inst in generated.instruments):
            raise ValueError("Model generated MIDI without notes")
        result = append_generated_tracks(source_midi, generated) if source_midi else generated
        write_midi(result, dst)
    if manifest:
        create_proposal(src, dst, manifest, locked_tracks=locked)
    return GenerationReport(
        model=model, candidate=dst, tracks=len(result.instruments),
        notes=sum(len(inst.notes) for inst in result.instruments),
        source=src, manifest=manifest, locked=tuple(locked),
        warnings=("Generated notes were aligned by musical beats, not acoustic similarity.",
                  "Original tracks and tempo map were preserved.") if src else (),
    )
