"""Model-neutral, review-first AI composition core (no network or weights).

The provider generates *new* tracks only. Musical beat positions are mapped
onto the source tempo map; the source MIDI is never modified or written here.
Use MIDIVOLT's existing review/proposal gate before publishing any candidate.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from math import isfinite
from numbers import Integral

import pretty_midi

from .providers import MidiGenerator
from .review_engine import inspect_arrangement

_MAX_SECONDS = 3600.0
_MAX_BEATS = 16384
_MAX_AUTOMATION = 50000


@dataclass(frozen=True)
class CompositionRequest:
    prompt: str
    locked_tracks: tuple[int, ...]
    seed: int | None = None
    max_new_tracks: int = 16
    max_new_notes: int = 20000


def compose_candidate(
    source: pretty_midi.PrettyMIDI,
    generator: MidiGenerator,
    request: CompositionRequest,
) -> tuple[pretty_midi.PrettyMIDI, dict]:
    """Append AI-generated instrument tracks, preserving all source tracks/maps.

    Return an in-memory candidate and the existing review engine's diff.
    This does not call an LLM by itself or approve/overwrite files.
    """
    if not isinstance(source, pretty_midi.PrettyMIDI):
        raise TypeError("Source must be a PrettyMIDI object.")
    if not isinstance(request, CompositionRequest):
        raise TypeError("request must be CompositionRequest.")
    if not isinstance(request.prompt, str) or not 1 <= len(request.prompt.strip()) <= 2048:
        raise ValueError("Prompt must contain 1..2048 non-whitespace characters.")
    if not isinstance(request.locked_tracks, tuple) or not request.locked_tracks:
        raise ValueError("At least one locked source track is required.")
    if len(set(request.locked_tracks)) != len(request.locked_tracks) or any(
        type(i) is not int or i < 0 or i >= len(source.instruments)
        for i in request.locked_tracks
    ):
        raise ValueError("Locked tracks must be unique existing source indices.")
    if type(request.max_new_tracks) is not int or not 1 <= request.max_new_tracks <= 64:
        raise ValueError("max_new_tracks must be within 1..64.")
    if type(request.max_new_notes) is not int or not 1 <= request.max_new_notes <= 100000:
        raise ValueError("max_new_notes must be within 1..100000.")
    if request.seed is not None and type(request.seed) is not int:
        raise ValueError("seed must be an integer or None.")
    if not callable(getattr(generator, "generate", None)):
        raise TypeError("Generator must implement generate(prompt, tempo=, seed=).")

    baseline = deepcopy(source)
    tempo = float(baseline.get_tempo_changes()[1][0])
    rendered = generator.generate(request.prompt.strip(), tempo=tempo, seed=request.seed)
    if not isinstance(rendered, pretty_midi.PrettyMIDI):
        raise TypeError("Generator must return a PrettyMIDI object.")
    if not 1 <= len(rendered.instruments) <= request.max_new_tracks:
        raise ValueError("Generator returned an invalid number of new tracks.")
    note_count = sum(len(inst.notes) for inst in rendered.instruments)
    automation_count = sum(
        len(inst.control_changes) + len(inst.pitch_bends)
        for inst in rendered.instruments
    )
    if not 1 <= note_count <= request.max_new_notes or automation_count > _MAX_AUTOMATION:
        raise ValueError("Generator exceeded the notes/automation budget or returned no notes.")

    def convert_time(seconds: float) -> float:
        if not isinstance(seconds, (int, float)) or not isfinite(seconds) or not 0 <= seconds <= _MAX_SECONDS:
            raise ValueError("Generated MIDI event time is invalid or exceeds one hour.")
        beat = rendered.time_to_tick(float(seconds)) / rendered.resolution
        if beat < 0 or beat > _MAX_BEATS:
            raise ValueError("Generated event exceeds the musical beat budget.")
        target_tick = round(beat * baseline.resolution)
        return float(baseline.tick_to_time(target_tick))

    candidate = deepcopy(baseline)
    for index, generated in enumerate(rendered.instruments):
        if (isinstance(generated.program, bool) or
                not isinstance(generated.program, Integral) or
                not 0 <= generated.program <= 127):
            raise ValueError("Generated track has an invalid MIDI program.")
        if len(generated.name) > 128:
            raise ValueError("Generated track name is too long.")
        track = deepcopy(generated)
        track.name = generated.name.strip() or f"AI Track {index + 1}"
        for note in track.notes:
            if (type(note.pitch) is not int or not 0 <= note.pitch <= 127 or
                type(note.velocity) is not int or not 1 <= note.velocity <= 127 or
                not isfinite(note.start) or not isfinite(note.end) or note.end <= note.start):
                raise ValueError("Generated note has invalid pitch, velocity or duration.")
            note.start, note.end = convert_time(note.start), convert_time(note.end)
            if note.end <= note.start:
                raise ValueError("Generated note collapsed when mapped to source ticks.")
        for cc in track.control_changes:
            if not 0 <= cc.number <= 127 or not 0 <= cc.value <= 127:
                raise ValueError("Generated control change is out of MIDI range.")
            cc.time = convert_time(cc.time)
        for bend in track.pitch_bends:
            if not -8192 <= bend.pitch <= 8191:
                raise ValueError("Generated pitch bend is out of MIDI range.")
            bend.time = convert_time(bend.time)
        candidate.instruments.append(track)

    review = inspect_arrangement(baseline, candidate, list(request.locked_tracks))
    return candidate, review
