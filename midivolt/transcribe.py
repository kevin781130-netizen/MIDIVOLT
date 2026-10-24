"""Batch stem-to-MIDI baseline using Spotify Basic Pitch.

Input WAV stems must share the same timeline, including their leading silence.
This engine handles pitched stems via Basic Pitch; optional drum DSP handles
kick, snare and closed hi-hat without pretending drum pitches are melody.
"""
from __future__ import annotations

import argparse
import copy
import json
import re
import sys
import tempfile
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import pretty_midi

# General MIDI program numbers are zero-based. These are playback labels,
# *not* instrument recognitions made by the model.
GM_PROGRAM = {"bass": 33, "guitar": 27, "keys": 0, "vocal": 53, "other": 0}
KEYWORDS = {
    "drums": (r"drums?", r"perc(?:ussion)?", r"kick", r"snare", r"hi[\s_-]?hat",
              "鼓", "ドラム", "打擊"),
    "bass": (r"bass", r"bassguitar", "貝斯", "贝斯", "ベース"),
    "guitar": (r"guitars?", r"gt(?:r)?", "吉他", "ギター"),
    "keys": (r"keys?", r"keyboards?", r"piano", r"synth", "鋼琴", "钢琴",
             "鍵盤", "键盘", "ピアノ", "キーボード"),
    "vocal": (r"vocals?", r"vox", r"voice", r"leadvox", "人聲", "人声",
              "ボーカル", "歌声"),
    "other": (r"other", "其他", "その他"),
}


@dataclass(frozen=True)
class Stem:
    path: Path
    kind: str


def detect_kind(filename: str) -> str | None:
    """Classify by stem filename only; never claim acoustic instrument recognition."""
    name = unicodedata.normalize("NFKC", Path(filename).stem).lower()
    matched: list[str] = []
    for kind, patterns in KEYWORDS.items():
        if any(
            (re.search(r"(?<![a-z])(?:" + word + r")(?![a-z])", name) is not None
             if word.isascii() else word in name)
            for word in patterns
        ):
            matched.append(kind)
    return matched[0] if len(matched) == 1 else None


def discover(input_path: Path, forced_type: str | None = None, *, drums_enabled: bool = False) -> tuple[list[Stem], list[dict]]:
    if not input_path.exists():
        raise ValueError(f"Input does not exist: {input_path}")
    if input_path.is_file():
        if input_path.suffix.lower() != ".wav":
            raise ValueError("Input file must be WAV.")
        files = [input_path]
    elif input_path.is_dir():
        if forced_type:
            raise ValueError("--stem-type is supported only with a single WAV file.")
        files = sorted(
            (p for p in input_path.iterdir() if p.is_file() and p.suffix.lower() == ".wav"),
            key=lambda p: p.name.casefold(),
        )
    else:
        raise ValueError(f"Input is not a file or directory: {input_path}")
    if not files:
        raise ValueError("No WAV files found in input folder.")

    stems: list[Stem] = []
    skipped: list[dict] = []
    for path in files:
        kind = forced_type or detect_kind(path.name)
        if kind == "drums" and not drums_enabled:
            skipped.append({"file": path.name, "reason": "drums_need_dedicated_engine"})
        elif kind is None:
            skipped.append({"file": path.name, "reason": "unrecognized_or_ambiguous_stem_name"})
        else:
            stems.append(Stem(path, kind))
    if not stems:
        raise ValueError("No pitched stems to transcribe. Drum stems require a dedicated engine.")
    # Avoid output collision on filesystems that are case-insensitive.
    names = [s.path.stem.casefold() for s in stems]
    if len(names) != len(set(names)):
        raise ValueError("WAV stems have colliding names ignoring case.")
    return stems, skipped


def basic_pitch_backend() -> Callable[[Path, float, float, float, float], pretty_midi.PrettyMIDI]:
    """Lazy-load the optional dependency and reuse one model for the whole batch."""
    try:
        from basic_pitch import ICASSP_2022_MODEL_PATH
        from basic_pitch.inference import Model, predict
    except (ImportError, AttributeError) as exc:
        raise RuntimeError(
            "Basic Pitch unavailable. Install with: pip install -r requirements-transcribe.txt"
        ) from exc

    model = Model(ICASSP_2022_MODEL_PATH)

    def run(path: Path, tempo: float, onset: float, frame: float, minimum_ms: float) -> pretty_midi.PrettyMIDI:
        _, midi, _ = predict(
            path,
            model_or_model_path=model,
            midi_tempo=tempo,
            onset_threshold=onset,
            frame_threshold=frame,
            minimum_note_length=minimum_ms,
        )
        return midi

    return run


def to_track(source: pretty_midi.PrettyMIDI, stem: Stem) -> pretty_midi.Instrument:
    """Copy note events unchanged in seconds, preserving bends and CCs."""
    track = pretty_midi.Instrument(
        program=GM_PROGRAM.get(stem.kind, 0), is_drum=stem.kind == "drums",
        name=f"{stem.kind} | {stem.path.stem}"
    )
    for instrument in source.instruments:
        track.notes.extend(copy.deepcopy(instrument.notes))
        track.pitch_bends.extend(copy.deepcopy(instrument.pitch_bends))
        track.control_changes.extend(copy.deepcopy(instrument.control_changes))
    track.notes.sort(key=lambda n: (n.start, n.pitch, n.end))
    return track


def transcribe_stems(
    input_path: Path,
    output_dir: Path,
    *,
    tempo: float = 120.0,
    onset: float = 0.5,
    frame: float = 0.3,
    minimum_note_ms: float = 127.7,
    stem_type: str | None = None,
    drum_engine: str = "off",
    overwrite: bool = False,
    predictor: Callable[[Path, float, float, float, float], pretty_midi.PrettyMIDI] | None = None,
) -> dict:
    if not (20.0 <= tempo <= 400.0):
        raise ValueError("--tempo must be between 20 and 400 BPM")
    if not (0.0 < onset < 1.0 and 0.0 < frame < 1.0):
        raise ValueError("Thresholds must be strictly between 0 and 1.")
    if minimum_note_ms <= 0:
        raise ValueError("--min-note-ms must be positive.")
    if drum_engine not in {"off", "dsp"}:
        raise ValueError("--drum-engine must be off or dsp.")

    input_path, output_dir = Path(input_path), Path(output_dir)
    stems, skipped = discover(input_path, stem_type, drums_enabled=(drum_engine == "dsp"))
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs = [output_dir / (s.path.stem + ".mid") for s in stems]
    combined_path = output_dir / "MIDIVOLT_multitrack.mid"
    report_path = output_dir / "MIDIVOLT_report.json"
    all_targets = outputs + [combined_path, report_path]
    if len({p.name.casefold() for p in all_targets}) != len(all_targets):
        raise ValueError("An input stem conflicts with a reserved output filename.")
    if not overwrite:
        existing = [str(path) for path in all_targets if path.exists()]
        if existing:
            raise FileExistsError("Refusing to overwrite: " + ", ".join(existing))

    run = (predictor or basic_pitch_backend()) if any(s.kind != "drums" for s in stems) else None
    combined = pretty_midi.PrettyMIDI(initial_tempo=tempo, resolution=960)
    records = []
    started = time.perf_counter()
    # Stage results so an inference exception does not leave partial outputs.
    with tempfile.TemporaryDirectory(prefix=".midivolt-", dir=output_dir) as temp:
        staging = Path(temp)
        for stem in stems:
            t0 = time.perf_counter()
            diagnostics = None
            if stem.kind == "drums":
                from midivolt.drums import transcribe_drum_wav
                source, diagnostics = transcribe_drum_wav(stem.path, tempo=tempo)
            else:
                source = run(stem.path, tempo, onset, frame, minimum_note_ms)
            if not isinstance(source, pretty_midi.PrettyMIDI):
                raise TypeError(f"Backend did not return PrettyMIDI for {stem.path.name}")
            track = to_track(source, stem)
            separate = pretty_midi.PrettyMIDI(initial_tempo=tempo, resolution=960)
            separate.instruments.append(copy.deepcopy(track))
            separate.write(str(staging / (stem.path.stem + ".mid")))
            combined.instruments.append(track)
            records.append({
                "source_wav": stem.path.name,
                "stem_type": stem.kind,
                "midi_file": stem.path.stem + ".mid",
                "track_name": track.name,
                "note_count": len(track.notes),
                "engine": "drum_dsp_v1" if stem.kind == "drums" else "spotify_basic_pitch",
                "drum_diagnostics": diagnostics,
                "inference_seconds": round(time.perf_counter() - t0, 3),
            })
        combined.write(str(staging / combined_path.name))
        report = {
            "engine": "spotify_basic_pitch_plus_drum_dsp" if any(s.kind == "drums" for s in stems) and run is not None else ("drum_dsp_v1" if run is None else "spotify_basic_pitch"),
            "mode": "unquantized_seconds_on_original_wav_timeline",
            "tempo_bpm_midi_grid_only": tempo,
            "parameters": {
                "onset_threshold": onset,
                "frame_threshold": frame,
                "minimum_note_ms": minimum_note_ms,
            },
            "tracks": records,
            "skipped": skipped,
            "total_seconds": round(time.perf_counter() - started, 3),
            "multitrack_file": combined_path.name,
            "warning": "Baseline only: not instrument separation or guaranteed note accuracy. "
                       "Drums require --drum-engine dsp; only kick/snare/closed-hat supported. "
                       "WAVs must already have synchronized start times.",
        }
        (staging / report_path.name).write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        for target in all_targets:
            (staging / target.name).replace(target)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="MIDIVOLT: batch pitched WAV stems to aligned MIDI tracks.")
    parser.add_argument("--input", type=Path, required=True, help="single WAV or folder with stems")
    parser.add_argument("--output", type=Path, required=True, help="directory for MIDI and report")
    parser.add_argument("--stem-type", choices=tuple(GM_PROGRAM) + ("drums",), help="override filename for a single WAV")
    parser.add_argument("--drum-engine", choices=("off", "dsp"), default="off", help="opt-in kick/snare/hat detection; no pretrained models")
    parser.add_argument("--tempo", type=float, default=120.0, help="MIDI grid BPM; does not quantize notes")
    parser.add_argument("--onset-threshold", type=float, default=0.5)
    parser.add_argument("--frame-threshold", type=float, default=0.3)
    parser.add_argument("--min-note-ms", type=float, default=127.7)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = transcribe_stems(
            args.input, args.output,
            tempo=args.tempo,
            onset=args.onset_threshold,
            frame=args.frame_threshold,
            minimum_note_ms=args.min_note_ms,
            stem_type=args.stem_type,
            drum_engine=args.drum_engine,
            overwrite=args.overwrite,
        )
    except (ValueError, OSError, RuntimeError, TypeError) as exc:
        print(f"MIDIVOLT ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
