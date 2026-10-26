"""MIDI Agent-style WORKFLOW FOUNDATION: bounded prompt -> editable MIDI.

This intentionally implements an original, deterministic music-theory
generator rather than claiming LLM intelligence or copying third-party
source, branding, prompts or weights. Pluggable verified AI providers
are a separate milestone. Every requested part is a distinct SMF track.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
from math import ceil, isfinite
import random
import re

import pretty_midi

MAJOR = (0, 2, 4, 5, 7, 9, 11)
MINOR = (0, 2, 3, 5, 7, 8, 10)
NOTE_PC = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
PARTS = ("chords", "melody", "bass", "drums")
KEY_RE = re.compile(
    r"(?<![A-Za-z])([A-Ga-g])([#b♯♭]?)[\s-]*(major|minor|maj|min)(?![A-Za-z])",
    re.I,
)
BARS_RE = re.compile(r"(?<!\d)(\d{1,2})\s*(?:bars?|measures?|小節)(?![A-Za-z])", re.I)
BPM_RE = re.compile(r"(?<!\d)(\d{2,3})\s*(?:bpm|拍/分)(?![A-Za-z])", re.I)


@dataclass(frozen=True)
class PromptSpec:
    prompt: str
    key: str
    mode: str
    bars: int
    bpm: float
    parts: tuple[str, ...]
    seed: int
    sparse: bool
    syncopated: bool
    rising: bool

    def __post_init__(self):
        if not 1 <= self.bars <= 32 or not 40 <= self.bpm <= 240:
            raise ValueError("bars must be 1..32 and BPM must be 40..240")
        if self.mode not in ("major", "minor") or self.key not in NOTE_PC and not (
            len(self.key) == 2 and self.key[0] in NOTE_PC and self.key[1] in "#b"
        ):
            raise ValueError("Invalid major/minor key")
        if not self.parts or any(p not in PARTS for p in self.parts):
            raise ValueError("No supported MIDI parts")
        if type(self.seed) is not int or not 0 <= self.seed < 2**32:
            raise ValueError("seed must be a 32-bit unsigned integer")


def parse_prompt(
    prompt: str, *, key: str | None = None,
    mode: str | None = None, bars: int | None = None,
    bpm: float | None = None, parts: tuple[str, ...] | None = None,
    seed: int | None = None,
) -> PromptSpec:
    if not isinstance(prompt, str) or not 1 <= len(prompt.strip()) <= 1500:
        raise ValueError("Prompt must contain 1..1500 characters")
    p = prompt.strip()
    lower = p.casefold()
    found = KEY_RE.search(p)
    chinese = re.search(r"([A-Ga-g])([#b♯♭]?)(大調|小調)", p)
    key_name = key if key is not None else (
        (found.group(1) + found.group(2)) if found
        else chinese.group(1) + chinese.group(2) if chinese else "C"
    )
    key_name = key_name[:1].upper() + key_name[1:].replace("♯", "#").replace("♭", "b")
    if mode is None:
        mode = ("minor" if (found and found.group(3).lower() in ("minor", "min"))
                else "minor" if chinese and chinese.group(3) == "小調"
                else "major")
    mode = mode.lower()
    if bars is None:
        bar_match = BARS_RE.search(p)
        bars = int(bar_match.group(1)) if bar_match else 4
    if bpm is None:
        tempo_match = BPM_RE.search(p)
        bpm = float(tempo_match.group(1)) if tempo_match else 120.0
    if parts is None:
        requested = []
        identifiers = {
            "chords": ("chord", "harmony", "harmonies", "和弦", "和聲"),
            "melody": ("melody", "lead", "hook", "旋律", "主旋律"),
            "bass": ("bass", "bassline", "貝斯", "低音"),
            "drums": ("drum", "beat", "percussion", "鼓", "打擊"),
        }
        # Whole song/arrangement explicitly asks for a full four-part sketch.
        full = any(token in lower for token in (
            "whole song", "full song", "full arrangement", "all parts",
            "全曲", "完整編曲", "全部聲部", "整首"
        ))
        for role, keywords in identifiers.items():
            if full or any(word in lower for word in keywords):
                requested.append(role)
        parts = tuple(requested) or PARTS
    if seed is None:
        seed = int.from_bytes(sha256(p.encode("utf-8")).digest()[:4], "big")
    return PromptSpec(
        prompt=p, key=key_name, mode=mode, bars=bars,
        bpm=float(bpm), parts=tuple(parts), seed=seed,
        sparse=any(x in lower for x in ("sparse", "minimal", "spacious", "簡約", "稀疏")),
        syncopated=any(x in lower for x in ("syncopat", "funk", "house", "swing", "切分", "律動")),
        rising=any(x in lower for x in ("rising", "climb", "build tension", "上行", "漸強")),
    )


def _tonic(spec: PromptSpec) -> int:
    root = NOTE_PC[spec.key[0]]
    accidental = (1 if spec.key.endswith("#") else -1 if spec.key.endswith("b") else 0)
    return (root + accidental) % 12


def _notes_for_chord(root_pc: int, scale: tuple[int, ...], degree: int) -> list[int]:
    # Diatonic thirds stacked from scale degrees, with octave wrapping.
    indexes = (degree, degree + 2, degree + 4)
    return [
        48 + root_pc + scale[j % 7] + (12 if j >= 7 else 0)
        for j in indexes
    ]


def generate_sketch(
    spec: PromptSpec, *, source: pretty_midi.PrettyMIDI | None = None,
) -> pretty_midi.PrettyMIDI:
    """Return separately editable chord/melody/bass/drum tracks.

    Existing source MIDI is deep-copied unchanged. Extension uses a constant
    tempo, 4/4 bar-aligned tail; complex source tempo/meter fails closed.
    """
    if not isinstance(spec, PromptSpec):
        raise ValueError("Expected validated PromptSpec")
    if source is not None:
        if not isinstance(source, pretty_midi.PrettyMIDI):
            raise ValueError("Source must be Standard MIDI")
        if any((x.numerator, x.denominator) != (4, 4)
               for x in source.time_signature_changes):
            raise ValueError("Extension currently supports 4/4 only")
        _, tempos = source.get_tempo_changes()
        if len(tempos) != 1:
            raise ValueError("Extension requires constant source tempo")
        if abs(float(tempos[0]) - spec.bpm) > 0.02:
            raise ValueError("Extension BPM must equal source MIDI tempo")
        result = deepcopy(source)
    else:
        result = pretty_midi.PrettyMIDI(initial_tempo=spec.bpm)
    sec_beat = 60.0 / spec.bpm
    sec_bar = 4.0 * sec_beat
    start_bar = (ceil((result.get_end_time() - 1e-7) / sec_bar)
                 if source is not None else 0)
    start_seconds = max(0, start_bar) * sec_bar
    tonic = _tonic(spec)
    scale = MINOR if spec.mode == "minor" else MAJOR
    roots = (0, 5, 2, 6) if spec.mode == "minor" else (0, 5, 3, 4)
    rng = random.Random(spec.seed)

    tracks = {
        "chords": pretty_midi.Instrument(program=0, name="MIDIVOLT | Chords"),
        "melody": pretty_midi.Instrument(program=80, name="MIDIVOLT | Melody"),
        "bass": pretty_midi.Instrument(program=33, name="MIDIVOLT | Bass"),
        "drums": pretty_midi.Instrument(program=0, is_drum=True, name="MIDIVOLT | Drums"),
    }

    def add(role: str, pitch: int, bar: int, beat: float, length: float, velocity: int):
        begin = start_seconds + (bar * 4 + beat) * sec_beat
        end = begin + length * sec_beat
        max_end = start_seconds + spec.bars * sec_bar
        if pitch < 0 or pitch > 127 or end > max_end + 1e-8 or end <= begin:
            raise ValueError("Invalid generated note pitch/duration")
        tracks[role].notes.append(pretty_midi.Note(
            velocity=velocity, pitch=pitch, start=begin, end=min(end, max_end)
        ))

    for bar in range(spec.bars):
        degree = roots[bar % 4]
        chord = _notes_for_chord(tonic, scale, degree)
        # Chords: triads, four beats long, no opaque generated audio.
        if "chords" in spec.parts:
            for pitch in chord:
                add("chords", pitch, bar, 0, 3.8, 70)
        if "bass" in spec.parts:
            pitch = 36 + (tonic + scale[degree]) % 12
            beats = (0, 2.5) if spec.syncopated else (0, 2)
            for beat in beats:
                add("bass", pitch, bar, beat, .75 if spec.syncopated else 1.75, 80)
        if "melody" in spec.parts:
            beats = (0.0, 2.0) if spec.sparse else (0.0, 1.0, 2.0, 3.0)
            for i, beat in enumerate(beats):
                # Generated melody stays in-key and references local harmony.
                step = ((bar + i) % 7) if spec.rising else rng.choice((degree, degree+2, degree+4)) % 7
                pitch = 60 + (tonic + scale[step]) % 12
                add("melody", pitch, bar, beat, .7 if not spec.sparse else 1.55,
                    70 + rng.randint(-8, 8))
        if "drums" in spec.parts:
            # Standard General MIDI drum note numbers.
            for beat in (0, 2):
                add("drums", 36, bar, beat, .16, 105)
            for beat in ((2,) if "half-time" in spec.prompt.lower() else (1, 3)):
                add("drums", 38, bar, beat, .13, 93)
            for h in range(8):
                add("drums", 42, bar, h * .5, .11,
                    69 if h % 2 else 78)
    for role in PARTS:
        if role in spec.parts:
            if not tracks[role].notes:
                raise ValueError("Requested part has no generated notes")
            result.instruments.append(tracks[role])
    return result


def report(spec: PromptSpec, midi: pretty_midi.PrettyMIDI, *, extended: bool) -> dict:
    return {
        "engine": "original_deterministic_music_theory_generator_v1",
        "llm_inference_used": False, "pretrained_weights_bundled": False,
        "original_midi_preserved": bool(extended),
        "key": spec.key, "mode": spec.mode, "bars_generated": spec.bars,
        "bpm": spec.bpm, "seed": spec.seed, "parts": list(spec.parts),
        "tracks_total": len(midi.instruments),
        "notes_total": sum(len(i.notes) for i in midi.instruments),
        "DAW_plugin_integration": False,
    }
