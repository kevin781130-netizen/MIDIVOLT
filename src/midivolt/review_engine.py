"""Reviewable, non-destructive MIDI arrangement proposals.

Supports any candidate MIDI generator, including external AI models. An
explicit lock list protects original tracks; global timing maps are locked.
No LLM or network client is bundled in this module.
"""
from __future__ import annotations

from collections import Counter
from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile

import pretty_midi

from .io import read_midi, write_midi

SCHEMA_VERSION = 1


def _digest(path: Path) -> str:
    with path.open("rb") as file:
        h = sha256()
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            h.update(chunk)
        return h.hexdigest()


def _event_time(reference: pretty_midi.PrettyMIDI, seconds: float) -> int:
    return int(reference.time_to_tick(seconds))


def _note_events(reference: pretty_midi.PrettyMIDI, instrument) -> Counter:
    return Counter((
        int(n.pitch), int(n.velocity),
        _event_time(reference, n.start),
        _event_time(reference, n.end),
    ) for n in instrument.notes)


def _automation_events(reference: pretty_midi.PrettyMIDI, instrument) -> tuple:
    cc = Counter((
        int(c.number), int(c.value), _event_time(reference, c.time)
    ) for c in instrument.control_changes)
    bend = Counter((
        int(b.pitch), _event_time(reference, b.time)
    ) for b in instrument.pitch_bends)
    return cc, bend


def _global_signature(midi: pretty_midi.PrettyMIDI) -> tuple:
    times, bpms = midi.get_tempo_changes()
    tempo = tuple((round(float(t), 6), round(float(bpm), 4))
                  for t, bpm in zip(times, bpms))
    meter = tuple((int(m.numerator), int(m.denominator),
                   round(float(m.time), 6))
                  for m in midi.time_signature_changes)
    key = tuple((int(k.key_number), round(float(k.time), 6))
                for k in midi.key_signature_changes)
    return tempo, meter, key


def inspect_arrangement(
    source: pretty_midi.PrettyMIDI,
    candidate: pretty_midi.PrettyMIDI,
    locked_tracks: list[int],
) -> dict:
    """Validate source/candidate and return note-level diff by track index.

    Track indexes intentionally remain significant. Rearranging instrument
    order changes the diff and cannot bypass a locked source track.
    """
    if _global_signature(source) != _global_signature(candidate):
        raise ValueError("Candidate changes tempo, meter or key map; global timing is locked.")
    if not locked_tracks or len(set(locked_tracks)) != len(locked_tracks):
        raise ValueError("Provide unique locked track indices (at least one).")
    if any(type(i) is not int or i < 0 or i >= len(source.instruments)
           for i in locked_tracks):
        raise ValueError("Locked track index is out of source MIDI range.")

    changes: list[dict] = []
    for idx in range(max(len(source.instruments), len(candidate.instruments))):
        before = source.instruments[idx] if idx < len(source.instruments) else None
        after = candidate.instruments[idx] if idx < len(candidate.instruments) else None
        old_notes = _note_events(source, before) if before else Counter()
        new_notes = _note_events(source, after) if after else Counter()
        removed = sum((old_notes - new_notes).values())
        added = sum((new_notes - old_notes).values())

        if idx in locked_tracks:
            if after is None or before is None:
                raise ValueError(f"Locked track {idx} was removed.")
            if (before.name, before.program, before.is_drum) != (
                after.name, after.program, after.is_drum
            ):
                raise ValueError(f"Locked track {idx} identity/instrument changed.")
            if old_notes != new_notes or (
                _automation_events(source, before) !=
                _automation_events(source, after)
            ):
                raise ValueError(f"Locked track {idx} MIDI events changed.")

        metadata_changed = bool(before and after and (
            (before.name, before.program, before.is_drum) !=
            (after.name, after.program, after.is_drum) or
            _automation_events(source, before) !=
            _automation_events(source, after)
        ))
        if added or removed or before is None or after is None or metadata_changed:
            changes.append({
                "track": idx,
                "before": before.name if before else None,
                "after": after.name if after else None,
                "notes_added": added,
                "notes_removed": removed,
                "metadata_or_automation_changed": metadata_changed,
                "locked": idx in locked_tracks,
            })
    return {
        "original_tracks": len(source.instruments),
        "candidate_tracks": len(candidate.instruments),
        "locked_tracks": list(locked_tracks),
        "notes_added": sum(t["notes_added"] for t in changes),
        "notes_removed": sum(t["notes_removed"] for t in changes),
        "tracks_changed": changes,
    }


def _distinct_paths(*paths: Path) -> None:
    resolved = [p.resolve() for p in paths]
    if len(set(resolved)) != len(resolved):
        raise ValueError("Input, candidate, manifest and output must be separate paths.")


def _save_new_json(path: Path, payload: dict) -> None:
    """Stage JSON then publish without truncating any existing manifest."""
    if path.suffix.lower() != ".json":
        raise ValueError("Proposal manifest must end with .json.")
    if not path.parent.is_dir():
        raise FileNotFoundError(f"Manifest directory missing: {path.parent}")
    if path.exists():
        raise FileExistsError(path)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    os.close(fd)
    try:
        Path(tmp).write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        os.link(tmp, path)
    finally:
        Path(tmp).unlink(missing_ok=True)


def create_proposal(
    input_path: str | Path, candidate_path: str | Path,
    manifest_path: str | Path, *, locked_tracks: list[int],
) -> dict:
    original = Path(input_path).resolve()
    candidate = Path(candidate_path).resolve()
    manifest = Path(manifest_path).resolve()
    _distinct_paths(original, candidate, manifest)
    review = inspect_arrangement(
        read_midi(original), read_midi(candidate), locked_tracks
    )
    proposal = {
        "schema_version": SCHEMA_VERSION,
        "source": str(original),
        "candidate": str(candidate),
        "source_sha256": _digest(original),
        "candidate_sha256": _digest(candidate),
        "locked_tracks": list(locked_tracks),
        "review": review,
    }
    _save_new_json(manifest, proposal)
    return proposal


def check_proposal(manifest_path: str | Path) -> tuple[dict, dict]:
    manifest = Path(manifest_path).resolve()
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("Invalid proposal JSON.") from exc
    if not isinstance(data, dict) or data.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("Unsupported proposal schema.")
    src, can = Path(data["source"]).resolve(), Path(data["candidate"]).resolve()
    _distinct_paths(src, can, manifest)
    if (_digest(src) != data["source_sha256"] or
            _digest(can) != data["candidate_sha256"]):
        raise ValueError("Source/candidate changed since proposal; create a new proposal.")
    report = inspect_arrangement(read_midi(src), read_midi(can), data["locked_tracks"])
    if report != data["review"]:
        raise ValueError("Proposal review mismatch; create a new proposal.")
    return data, report


def apply_proposal(
    manifest_path: str | Path, output_path: str | Path,
    *, approved: bool,
) -> dict:
    if not approved:
        raise PermissionError("Arrangement must be explicitly approved with --approve.")
    manifest = Path(manifest_path).resolve()
    data, report = check_proposal(manifest)
    dest = Path(output_path).resolve()
    _distinct_paths(
        Path(data["source"]), Path(data["candidate"]), manifest, dest,
    )
    # Never overwrite an existing project, and revalidate immediately prior to publish.
    if dest.exists():
        raise FileExistsError(f"Output already exists: {dest}")
    write_midi(read_midi(data["candidate"]), dest)
    return {**report, "output": str(dest), "approved": True}
