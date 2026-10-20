"""Validated MIDI I/O with crash-safe atomic writes."""

from __future__ import annotations

import os
from pathlib import Path
import tempfile

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
    """Serialize to a sibling temporary file and publish only once complete.

    For an existing file, an exception during serialization never truncates
    the original. In no-overwrite mode, an atomic hard-link operation refuses
    a target created concurrently, preventing accidental replacement.
    """
    target = Path(path)
    if target.suffix.lower() not in {".mid", ".midi"}:
        raise ValueError("Output must use .mid or .midi.")
    if not target.parent.is_dir():
        raise FileNotFoundError(f"Output directory does not exist: {target.parent}")
    if target.exists() and not overwrite:
        raise FileExistsError(f"Refusing to overwrite {target}; use --overwrite.")

    fd, temp_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
    )
    os.close(fd)
    staged = Path(temp_name)
    try:
        midi.write(str(staged))
        if overwrite:
            os.replace(staged, target)
        else:
            try:
                os.link(staged, target)
            except FileExistsError as exc:
                raise FileExistsError(
                    f"Refusing to overwrite {target}; use --overwrite."
                ) from exc
        return target
    finally:
        staged.unlink(missing_ok=True)
