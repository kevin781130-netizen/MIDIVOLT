"""Validated MIDI I/O with crash-safe atomic writes."""

from __future__ import annotations

import os
from pathlib import Path
import tempfile

import pretty_midi


def _latin1_safe_names(midi: pretty_midi.PrettyMIDI) -> pretty_midi.PrettyMIDI:
    """pretty_midi 以 latin-1 編碼軌名；非 Latin-1 名稱（中文、emoji）會 UnicodeEncodeError。

    此類名稱改以 UTF-8 位元組寫入（Cubase 等 DAW 的慣例）。可 latin-1 編碼的名稱原樣保留，
    因此由檔案讀入的軌名往返位元組不變；不修改呼叫者的物件。
    """
    def unsafe(name: str) -> bool:
        try:
            name.encode("latin-1")
            return False
        except UnicodeEncodeError:
            return True

    instruments = getattr(midi, "instruments", ())
    if not any(unsafe(inst.name) for inst in instruments):
        return midi
    from copy import deepcopy

    safe = deepcopy(midi)
    for inst in safe.instruments:
        if unsafe(inst.name):
            inst.name = inst.name.encode("utf-8").decode("latin-1")
    return safe


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
        _latin1_safe_names(midi).write(str(staged))
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
