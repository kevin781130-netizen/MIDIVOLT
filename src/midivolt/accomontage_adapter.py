"""Opt-in AccoMontage MIDI-only bridge. Never imports or executes upstream code.

No checkpoint, dataset, pickle, torch, network access or third-party source
is loaded by this module. External inference is an operator-controlled step.
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import argparse
import json
import math
import os
from pathlib import Path
import re
import sys
import tempfile

import pretty_midi

from .io import read_midi
from .model_adapters import append_generated_tracks
from .review_engine import create_proposal, inspect_arrangement

SCHEMA = "midivolt-accomontage-bridge/v1"


def _hash(path: Path) -> str:
    h = sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _existing_file(path: str | Path, label: str) -> Path:
    p = Path(path).expanduser().resolve(strict=True)
    if not p.is_file():
        raise ValueError(f"{label} must be a file")
    return p


def _sections(text: str) -> int:
    if not isinstance(text, str):
        raise ValueError("segments must be a phrase string (e.g. A8B8)")
    parts = re.findall(r"[A-Za-z](?:[1-9]|1[0-6])", text)
    if not parts or "".join(parts) != text:
        raise ValueError("segments must be letter+1..16 bars, e.g. A8B8")
    return sum(int(p[1:]) for p in parts)


def _source_contract(midi: pretty_midi.PrettyMIDI, melody: int, chords: int,
                     segments: str) -> dict:
    if melody == chords or min(melody, chords) < 0 or max(melody, chords) >= len(midi.instruments):
        raise ValueError("melody/chords must be distinct existing track indexes")
    tracks = (midi.instruments[melody], midi.instruments[chords])
    if any(t.is_drum or not t.notes for t in tracks):
        raise ValueError("melody and chord tracks must contain pitched MIDI notes")
    signatures = midi.time_signature_changes
    if any(s.numerator != 4 or s.denominator != 4 or s.time > 1e-6 for s in signatures):
        raise ValueError("v1 accepts only a constant 4/4 meter from time zero")
    change_times, bpms = midi.get_tempo_changes()
    if len(bpms) != 1 or len(change_times) != 1 or not math.isfinite(float(bpms[0])):
        raise ValueError("v1 accepts a single constant tempo")
    bpm = float(bpms[0])
    bar_seconds = 240.0 / bpm
    last_note_end = max(note.end for track in tracks for note in track.notes)
    bars = math.ceil(last_note_end / bar_seconds - 1e-8)
    if bars <= 0 or bars != _sections(segments):
        raise ValueError(f"segments must cover exactly {bars} input bars; no truncation/padding")
    if any(note.start < 0 or note.end <= note.start for track in tracks for note in track.notes):
        raise ValueError("invalid source note timing")
    return {"bars": bars, "bpm": bpm}


def prepare(*, source: str | Path, workdir: str | Path, melody_track: int,
            chord_track: int, segments: str) -> dict:
    """Build a minimal lead sheet in a NEW folder; never run AccoMontage."""
    src = _existing_file(source, "source MIDI")
    midi = read_midi(src)
    info = _source_contract(midi, melody_track, chord_track, segments)
    directory = Path(workdir).expanduser().resolve()
    if directory == src.parent or src.is_relative_to(directory):
        raise ValueError("workdir must not contain or equal the source MIDI path")
    if directory.exists():
        raise FileExistsError("workdir must be a new, nonexistent directory")
    if not directory.parent.is_dir():
        raise FileNotFoundError("workdir parent directory must exist")
    directory.mkdir()
    try:
        stage = directory / "lead sheet.mid"
        pair = deepcopy(midi)
        pair.instruments = [deepcopy(midi.instruments[melody_track]),
                            deepcopy(midi.instruments[chord_track])]
        pair.write(str(stage))
        request = {
            "schema": SCHEMA,
            "source": str(src),
            "source_sha256": _hash(src),
            "lead_sheet": str(stage),
            "lead_sheet_sha256": _hash(stage),
            "upstream_melody_track": 0,
            "source_melody_track": melody_track,
            "source_chord_track": chord_track,
            "segmentation": segments,
            **info,
            "inference": "NOT_RUN",
            "license_gate": "UNVERIFIED",
        }
        (directory / "request.json").write_text(
            json.dumps(request, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return request
    except Exception:
        # Only files created in this fresh folder may be removed.
        for p in directory.iterdir():
            if p.is_file():
                p.unlink()
        directory.rmdir()
        raise


def ingest(*, request: str | Path, generated: str | Path, accompaniment_track: int,
           output: str | Path, manifest: str | Path) -> dict:
    """Import only an explicitly selected external accompaniment, for review."""
    req = _existing_file(request, "request JSON")
    data = json.loads(req.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema") != SCHEMA:
        raise ValueError("unsupported request schema")
    src = _existing_file(data["source"], "source MIDI")
    stage = _existing_file(data["lead_sheet"], "staged lead sheet")
    if req != stage.parent / "request.json":
        raise ValueError("request must be next to its staged lead sheet")
    if _hash(src) != data["source_sha256"] or _hash(stage) != data["lead_sheet_sha256"]:
        raise ValueError("source or staged MIDI changed since prepare")
    source_midi = read_midi(src)
    _source_contract(source_midi, data["source_melody_track"],
                     data["source_chord_track"], data["segmentation"])
    raw = _existing_file(generated, "generated MIDI")
    dst = Path(output).expanduser().resolve()
    man = Path(manifest).expanduser().resolve()
    paths = [src, stage, req, raw, dst, man]
    if len(paths) != len(set(paths)):
        raise ValueError("source, request, generated, candidate, manifest must differ")
    if dst.suffix.lower() not in (".mid", ".midi") or man.suffix.lower() != ".json":
        raise ValueError("candidate must be MIDI and manifest must be JSON")
    if not dst.parent.is_dir() or not man.parent.is_dir():
        raise FileNotFoundError("output and manifest directories must exist")
    if dst.exists() or man.exists():
        raise FileExistsError("candidate or manifest already exists")
    generated_midi = read_midi(raw)
    if (type(accompaniment_track) is not int or accompaniment_track < 0 or
            accompaniment_track >= len(generated_midi.instruments)):
        raise ValueError("invalid accompaniment track index")
    selected = generated_midi.instruments[accompaniment_track]
    if not selected.notes or selected.is_drum:
        raise ValueError("selected accompaniment must contain pitched notes")
    # Avoid appending upstream's copy of the source melody.
    generated_midi.instruments = [deepcopy(selected)]
    candidate = append_generated_tracks(source_midi, generated_midi)
    locks = [data["source_melody_track"]]
    inspect_arrangement(source_midi, candidate, locks)
    # Exclusive publish: neither candidate nor manifest can overwrite user data.
    fd, temp_name = tempfile.mkstemp(prefix=".midivolt-acco-", suffix=".mid", dir=dst.parent)
    os.close(fd)
    temp = Path(temp_name)
    published = False
    try:
        candidate.write(str(temp))
        os.link(temp, dst)
        published = True
        result = create_proposal(src, dst, man, locked_tracks=locks)
    except Exception:
        if published:
            dst.unlink()
        raise
    finally:
        temp.unlink(missing_ok=True)
    return {
        "candidate": str(dst), "manifest": str(man),
        "selected_generated_track": accompaniment_track,
        "source_melody_locked": locks,
        "notes_added": result["review"]["notes_added"],
        "release_approved": False, "inference_verified": False,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m midivolt.accomontage_adapter")
    sub = p.add_subparsers(dest="command", required=True)
    a = sub.add_parser("prepare", help="Stage safe MIDI input; does not run inference")
    a.add_argument("--source", required=True)
    a.add_argument("--workdir", required=True, help="new/nonexistent directory")
    a.add_argument("--melody-track", type=int, required=True)
    a.add_argument("--chord-track", type=int, required=True)
    a.add_argument("--segments", required=True)
    b = sub.add_parser("ingest", help="Build a reviewable candidate from external MIDI")
    b.add_argument("--request", required=True)
    b.add_argument("--generated", required=True)
    b.add_argument("--accompaniment-track", type=int, required=True)
    b.add_argument("--out", required=True)
    b.add_argument("--manifest", required=True)
    x = p.parse_args(argv)
    try:
        if x.command == "prepare":
            result = prepare(source=x.source, workdir=x.workdir, melody_track=x.melody_track,
                             chord_track=x.chord_track, segments=x.segments)
        else:
            result = ingest(request=x.request, generated=x.generated,
                            accompaniment_track=x.accompaniment_track,
                            output=x.out, manifest=x.manifest)
    except (ValueError, OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f"MIDIVOLT AccoMontage adapter: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
