"""Strict, review-first per-instrument MIDI composition.

Runs a model once per explicitly planned role and refuses extra/misprogrammed
tracks. A MIDI program flag is *not* proof of acoustic or musical correctness.
No audio models/weights, network clients, or DAW code are bundled here.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Mapping

import pretty_midi

from .composition_engine import CompositionRequest, compose_candidate
from .composition_planner import make_composition_plan
from .review_engine import inspect_arrangement

# GM program numbers are zero-based. Ambiguous roles require an explicit
# program choice, restricted to their instrument family.
_PROGRAM_FAMILIES = {
    "bass": range(32, 40),
    "guitar": range(24, 32),
    "keys": tuple(range(0, 8)) + tuple(range(80, 104)),
    "woodwinds": range(68, 80),
}
_MAX_TOTAL_NOTES = 100000


def parse_program_assignments(values: list[str] | None) -> dict[str, int]:
    """Parse repeatable --program ROLE=GM, refusing duplicate or invalid keys."""
    assignments: dict[str, int] = {}
    for value in values or []:
        if not isinstance(value, str) or value.count("=") != 1:
            raise ValueError("--program must have the form role=0..127.")
        role, number = (part.strip() for part in value.split("=", 1))
        if not role or not number.isascii() or not number.isdecimal():
            raise ValueError("--program must contain a role and integer GM program.")
        if role in assignments:
            raise ValueError(f"Duplicate --program for role {role!r}.")
        gm = int(number)
        if not 0 <= gm <= 127:
            raise ValueError("GM programs must be within 0..127.")
        assignments[role] = gm
    return assignments


def _expected_programs(parts: list[dict], programs: Mapping[str, int]) -> dict[str, int | None]:
    roles = {part["role"] for part in parts}
    if not isinstance(programs, Mapping):
        raise TypeError("Program assignments must be a mapping.")
    extras = set(programs) - roles
    if extras:
        raise ValueError("Program assignment for unrequested role: " + ", ".join(sorted(extras)))
    expected: dict[str, int | None] = {}
    for part in parts:
        role = part["role"]
        selected = programs.get(role)
        if selected is not None and (type(selected) is not int or not 0 <= selected <= 127):
            raise ValueError(f"Invalid GM program for {role}.")
        if part["is_drum"]:
            if selected is not None:
                raise ValueError("Drum kit requires is_drum=true, not a pitched GM program.")
            expected[role] = None
        elif part["gm_program_hint"] is not None:
            hint = part["gm_program_hint"]
            if selected is not None and selected != hint:
                raise ValueError(f"{role} requires GM program {hint}.")
            expected[role] = hint
        else:
            if selected is None:
                raise ValueError(f"{role} requires explicit --program {role}=GM.")
            if selected not in _PROGRAM_FAMILIES[role]:
                raise ValueError(f"GM program {selected} is outside the allowed {role} family.")
            expected[role] = selected
    return expected


def compose_strict_parts(
    source: pretty_midi.PrettyMIDI,
    prompt: str,
    generator,
    *,
    locked_tracks: tuple[int, ...],
    program_assignments: Mapping[str, int] | None = None,
    seed: int | None = None,
    max_new_tracks: int = 16,
    max_total_notes: int = 20000,
) -> tuple[pretty_midi.PrettyMIDI, dict, dict]:
    """Generate one validated MIDI track per explicitly requested instrument.

    All preflight checks run BEFORE any generator call. If any part fails, this
    function raises without publishing a partial candidate; the caller writes
    files only after the entire process succeeds.
    """
    if not isinstance(source, pretty_midi.PrettyMIDI):
        raise TypeError("source must be PrettyMIDI.")
    if type(max_new_tracks) is not int or not 1 <= max_new_tracks <= 64:
        raise ValueError("max_new_tracks must be between 1 and 64.")
    if type(max_total_notes) is not int or not 1 <= max_total_notes <= _MAX_TOTAL_NOTES:
        raise ValueError("max_total_notes must be between 1 and 100000.")
    if seed is not None and (type(seed) is not int or not 0 <= seed < 2**31):
        raise ValueError("Seed must be a nonnegative 31-bit integer.")
    plan = make_composition_plan(
        prompt, source_track_count=len(source.instruments), locked_tracks=locked_tracks
    )
    parts = plan["parts"]
    if len(parts) > max_new_tracks:
        raise ValueError("Requested instrument count exceeds max_new_tracks.")
    expected = _expected_programs(parts, program_assignments or {})
    if seed is not None and seed + len(parts) - 1 >= 2**31:
        raise ValueError("Per-part seeds exceed supported 31-bit range.")
    if not callable(getattr(generator, "generate", None)):
        raise TypeError("generator must implement generate().")

    combined = deepcopy(source)
    remaining = max_total_notes
    for idx, part in enumerate(parts):
        role = part["role"]
        if remaining <= 0:
            raise ValueError("Total composition note budget exceeded.")
        one, _ = compose_candidate(
            source,
            generator,
            CompositionRequest(
                prompt=part["instruction"],
                locked_tracks=locked_tracks,
                seed=seed + idx if seed is not None else None,
                max_new_tracks=1,
                max_new_notes=remaining,
            ),
        )
        # compose_candidate appends to a copy of the unchanged original.
        new_tracks = one.instruments[len(source.instruments):]
        if len(new_tracks) != 1:
            raise ValueError(f"{role}: model returned multiple/zero tracks.")
        track = new_tracks[0]
        if not track.notes:
            raise ValueError(f"{role}: model returned an empty part.")
        if bool(track.is_drum) != bool(part["is_drum"]):
            raise ValueError(f"{role}: drum-channel classification mismatch.")
        expected_gm = expected[role]
        if not part["is_drum"] and track.program != expected_gm:
            raise ValueError(f"{role}: expected GM {expected_gm}, got {track.program}.")
        if part["is_drum"] and any(not 35 <= n.pitch <= 81 for n in track.notes):
            raise ValueError("drums: note outside the General MIDI percussion range 35..81.")
        remaining -= len(track.notes)
        track.name = f"MIDIVOLT AI | {idx + 1:02d} {part['label']}"
        combined.instruments.append(track)

    report = inspect_arrangement(source, combined, list(locked_tracks))
    if report["notes_removed"] or report["notes_added"] != max_total_notes - remaining:
        raise ValueError("Unexpected source note change or new MIDI event count.")
    return combined, plan, report
