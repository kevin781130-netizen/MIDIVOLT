"""Isolated optional ADT_STR bridge for MIDI drum-stem experiments.

No weights or third-party source are vendored into MIDIVOLT. The user must
explicitly opt into an un-cleared experimental run, install ADT_STR separately
and point to a local checkpoint. No network or shell commands are used.
"""
from __future__ import annotations

import math
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable

import pretty_midi


def transcribe_adt_str(
    audio_path: Path,
    *,
    tempo: float,
    repo_root: Path | None,
    checkpoint: Path | None,
    python_executable: str | Path | None = None,
    research_only: bool = False,
    timeout_s: int = 1200,
    runner: Callable = subprocess.run,
) -> tuple[pretty_midi.PrettyMIDI, dict]:
    """Run independently installed ADT_STR on an isolated WAV.

    No automatic install or download, and no commercial-release permission is
    inferred from a caller's flag. Model/core licensing is a separate gate.
    """
    if not research_only:
        raise PermissionError(
            "ADT_STR is research-only in MIDIVOLT until its code, checkpoint, "
            "share-alike obligations and commercial product distribution are reviewed. "
            "To benchmark explicitly, pass --research-only."
        )
    if repo_root is None or checkpoint is None:
        raise ValueError("ADT_STR requires --adt-root and --adt-checkpoint.")
    if not 20 <= tempo <= 400 or not math.isfinite(tempo):
        raise ValueError("tempo must be finite and between 20 and 400")
    if timeout_s < 1 or timeout_s > 14400:
        raise ValueError("ADT_STR timeout must be between 1 and 14400 seconds.")

    source = Path(audio_path).expanduser().resolve()
    root = Path(repo_root).expanduser().resolve()
    checkpoint_dir = Path(checkpoint).expanduser().resolve()
    entrypoint = root / "inference.py"
    if not source.is_file() or source.suffix.lower() != ".wav":
        raise ValueError("ADT_STR input must be an existing WAV.")
    if not entrypoint.is_file():
        raise ValueError("ADT_STR repo root must contain inference.py.")
    if not checkpoint_dir.is_dir():
        raise ValueError("ADT_STR checkpoint must be a local directory.")
    exe = str(python_executable) if python_executable else sys.executable

    with tempfile.TemporaryDirectory(prefix="midivolt-adt-str-") as tmp:
        command = [
            exe, str(entrypoint),
            "--input", str(source),
            "--checkpoint", str(checkpoint_dir),
            "--output_path", tmp,
        ]
        try:
            # No shell, no ambient network fetch. The specified *local* upstream
            # inference script is executed under its own trusted environment.
            result = runner(
                command,
                cwd=str(root),
                check=True,
                capture_output=True,
                text=True,
                timeout=timeout_s,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("ADT_STR inference timed out.") from exc
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or "")[-1500:]
            raise RuntimeError("ADT_STR inference failed: " + stderr) from exc
        expected = Path(tmp) / (source.stem + ".mid")
        if not expected.is_file():
            raise RuntimeError(f"ADT_STR failed to create MIDI for {source.name}.")
        try:
            raw = pretty_midi.PrettyMIDI(str(expected))
        except (EOFError, OSError, ValueError) as exc:
            raise RuntimeError("ADT_STR emitted an unreadable MIDI.") from exc
        if not raw.instruments or any(not ins.is_drum for ins in raw.instruments):
            raise RuntimeError("ADT_STR output must contain drum-only MIDI tracks.")
        for ins in raw.instruments:
            for note in ins.notes:
                if not (
                    0 <= note.pitch <= 127
                    and 1 <= note.velocity <= 127
                    and math.isfinite(note.start)
                    and math.isfinite(note.end)
                    and 0 <= note.start < note.end
                ):
                    raise RuntimeError("ADT_STR emitted invalid or negative-time MIDI notes.")
        count = sum(len(ins.notes) for ins in raw.instruments)
        histogram: dict[str, int] = {}
        for ins in raw.instruments:
            for n in ins.notes:
                histogram[str(n.pitch)] = histogram.get(str(n.pitch), 0) + 1
        diagnostics = {
            "engine": "adt_str",
            "license_gate": "research_only",
            "checkpoint_local": True,
            "detected": count,
            "raw_vendor_pitch_histogram": histogram,
            "pitch_namespace": "adt_str_vendor_custom_drum_classes",
            "standard_gm_output": False,
            "requires_explicit_daw_drum_mapping": True,
            "upstream_stdout_tail": (getattr(result, "stdout", "") or "")[-300:],
            "warning": (
                "External local ADT_STR uses a reduced/custom drum label vocabulary; "
                "raw numeric note pitches are NOT guaranteed to be General MIDI "
                "instrument assignments. Apply a verified mapping before DAW playback. "
                "Code/checkpoint licensing and commercial redistribution remain uncleared."
            ),
        }
        return raw, diagnostics
