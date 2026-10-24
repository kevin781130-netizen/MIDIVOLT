"""Strict, review-first per-instrument MIDI composition.

Runs a model once per explicitly planned role and refuses extra/misprogrammed
tracks. A MIDI program flag is *not* proof of acoustic or musical correctness.
No audio models/weights, network clients, or DAW code are bundled here.
"""
from __future__ import annotations

from copy import deepcopy
from math import isfinite
from typing import Mapping

import pretty_midi

from .composition_engine import CompositionRequest, compose_candidate
from .composition_planner import make_composition_plan
from .part_quality import evaluate_part_structure
from .harmony_quality import prepare_harmonic_context, evaluate_part_harmony
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
    minimum_structure_score: float = 0.75,
    quality_retries: int = 0,
    harmonic_key: str | None = None,
    harmonic_chords: str | None = None,
    beats_per_chord: float = 4.0,
    minimum_harmony_score: float | None = None,
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
    if type(minimum_structure_score) not in (float, int) or not isfinite(minimum_structure_score) or not 0 <= minimum_structure_score <= 1:
        raise ValueError("minimum_structure_score must be finite and within 0..1.")
    if type(quality_retries) is not int or not 0 <= quality_retries <= 3:
        raise ValueError("quality_retries must be between 0 and 3.")
    if minimum_harmony_score is not None and (
        type(minimum_harmony_score) not in (int, float)
        or not isfinite(minimum_harmony_score)
        or not 0 <= minimum_harmony_score <= 1
    ):
        raise ValueError("minimum_harmony_score must be finite in 0..1.")
    harmony_context = prepare_harmonic_context(
        key=harmonic_key, chords=harmonic_chords, beats_per_chord=beats_per_chord
    )
    if minimum_harmony_score is not None and harmony_context is None:
        raise ValueError("Harmony threshold requires explicit --harmonic-key or --harmonic-chords.")
    plan = make_composition_plan(
        prompt, source_track_count=len(source.instruments), locked_tracks=locked_tracks
    )
    parts = plan["parts"]
    if len(parts) > max_new_tracks:
        raise ValueError("Requested instrument count exceeds max_new_tracks.")
    expected = _expected_programs(parts, program_assignments or {})
    attempts_per_part = quality_retries + 1
    if seed is not None and seed + len(parts) * attempts_per_part - 1 >= 2**31:
        raise ValueError("Per-part seeds exceed supported 31-bit range.")
    if not callable(getattr(generator, "generate", None)):
        raise TypeError("generator must implement generate().")

    combined = deepcopy(source)
    remaining = max_total_notes
    quality_attempts: list[dict] = []
    for idx, part in enumerate(parts):
        role = part["role"]
        if remaining <= 0:
            raise ValueError("Total composition note budget exceeded.")

        for attempt in range(attempts_per_part):
            # Seeds are deterministic and unique across both roles and retries.
            attempt_seed = (
                seed + idx * attempts_per_part + attempt
                if seed is not None else None
            )
            one, _ = compose_candidate(
                source,
                generator,
                CompositionRequest(
                    prompt=part["instruction"],
                    locked_tracks=locked_tracks,
                    seed=attempt_seed,
                    max_new_tracks=1,
                    max_new_notes=remaining,
                ),
            )
            new_tracks = one.instruments[len(source.instruments):]
            if len(new_tracks) != 1:
                raise ValueError(f"{role}: model returned multiple/zero tracks.")
            track = new_tracks[0]
            if not track.notes:
                raise ValueError(f"{role}: model returned an empty part.")

            reason = ""
            if bool(track.is_drum) != bool(part["is_drum"]):
                reason = f"{role}: drum-channel classification mismatch."
            elif not part["is_drum"] and track.program != expected[role]:
                reason = f"{role}: expected GM {expected[role]}, got {track.program}."
            elif part["is_drum"] and any(not 35 <= n.pitch <= 81 for n in track.notes):
                reason = "drums: note outside the General MIDI percussion range 35..81."

            metrics = None if reason else evaluate_part_structure(source, track, role)
            if metrics is not None and metrics["score"] < minimum_structure_score:
                reason = (
                    f"{role}: MIDI structural score {metrics['score']:.4f} "
                    f"below threshold {minimum_structure_score:.4f} "
                    f"({', '.join(metrics['warnings']) or 'no classified warning'})."
                )
            harmonic_metrics = None
            if not reason and harmony_context is not None:
                harmonic_metrics = evaluate_part_harmony(
                    source, track, role, harmony_context,
                    reference_tracks=locked_tracks,
                )
                if (minimum_harmony_score is not None
                        and harmonic_metrics["score"] is not None
                        and harmonic_metrics["score"] < minimum_harmony_score):
                    reason = (
                        f"{role}: symbolic harmony score {harmonic_metrics['score']:.4f} "
                        f"below threshold {minimum_harmony_score:.4f}."
                    )
            quality_attempts.append({
                "role": role,
                "attempt": attempt + 1,
                "seed": attempt_seed,
                "accepted": not reason,
                "metrics": metrics,
                "harmony_metrics": harmonic_metrics,
                "reason": reason or None,
            })
            if reason:
                if attempt < quality_retries:
                    continue
                raise ValueError(
                    f"{reason} Rejected after {attempt + 1} attempt(s); "
                    "no partial candidate published."
                )

            remaining -= len(track.notes)
            track.name = f"MIDIVOLT AI | {idx + 1:02d} {part['label']}"
            combined.instruments.append(track)
            break

    plan["quality_policy"] = {
        "metric_type": "symbolic_structure_only",
        "minimum_structure_score": float(minimum_structure_score),
        "quality_retries": quality_retries,
        "harmony_key": harmony_context["key"] if harmony_context else None,
        "harmony_chords": [c["symbol"] for c in harmony_context["chords"]] if harmony_context else [],
        "beats_per_chord": harmony_context["beats_per_chord"] if harmony_context else None,
        "minimum_harmony_score": minimum_harmony_score,
        "harmony_gating_enabled": minimum_harmony_score is not None,
    }
    plan["quality_attempts"] = quality_attempts
    report = inspect_arrangement(source, combined, list(locked_tracks))
    if report["notes_removed"] or report["notes_added"] != max_total_notes - remaining:
        raise ValueError("Unexpected source note change or new MIDI event count.")
    return combined, plan, report
