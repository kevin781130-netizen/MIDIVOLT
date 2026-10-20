"""MIDI file safety and serialization helpers."""

from __future__ import annotations

from pathlib import Path

import pretty_midi


def read_midi(path: str | Path) -> pretty_midi.PrettyMIDI:
    source = Path(path)
    if source.suffix.lower() not in {".mid", ".midi"}:
        raise ValueError("Input must be a .mid or .midi file.")
    if not source.is_file():
        raise FileNotFoundError(source)
    return pretty_midi.PrettyMIDI(str(source))


def write_midi(
    midi: pretty_midi.PrettyMIDI, path: str | Path, *, overwrite: bool = False
) -> Path:
    target = Path(path)
    if target.suffix.lower() not in {".mid", ".midi"}:
        raise ValueError("Output must use .mid or .midi.")
    if target.exists() and not overwrite:
        raise FileExistsError(f"Refusing to overwrite {target}; use --overwrite.")
    if not target.parent.is_dir():
        raise FileNotFoundError(f"Output directory does not exist: {target.parent}")
    midi.write(str(target))
    return target
