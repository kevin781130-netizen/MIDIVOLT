"""MIDIVOLT drum-ontology benchmark v1: frozen 26-class ADT_STR vocabulary.

Source-of-truth: pier-maker92/ADT_STR, commit
77dbef225e7029478ebfb916f20c7a00274f0f12,
utils/mapping_utils.py::GM_standard_midi_to_Gm_custom_Mapping.
The map is fixed BEFORE scoring; it is not inferred from held-out E-GMD
notes or optimized to improve either model's F1.

Research scores only: this is NOT a standard-GM MIDI-export converter.
All input MIDI notes and timestamps remain unchanged.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections import Counter, defaultdict
from typing import Literal

import pretty_midi

from midivolt.compare_drums import drum_events
from midivolt.evaluate import Event, matching, score

ONTOLOGY_ID = "adt_str_26_class_source_frozen_v1"
UPSTREAM_SOURCE_SHA = "77dbef225e7029478ebfb916f20c7a00274f0f12"
# Pin the exact 47-entry published source mapping (GM 35..81 inclusive).
GM_TO_VENDOR = {
    35: 35, 36: 36, 37: 37, 38: 38, 39: 39, 40: 40, 41: 41,
    42: 42, 43: 41, 44: 43, 45: 41, 46: 44, 47: 45, 48: 45,
    49: 46, 50: 47, 51: 48, 52: 49, 53: 48, 54: 50, 55: 51,
    56: 52, 57: 46, 58: 53, 59: 48, 60: 54, 61: 54, 62: 54,
    63: 54, 64: 54, 65: 54, 66: 54, 67: 52, 68: 52, 69: 55,
    70: 55, 71: 56, 72: 56, 73: 57, 74: 57, 75: 58, 76: 58,
    77: 58, 78: 59, 79: 59, 80: 60, 81: 60,
}
VENDOR_CLASS_NAMES = {
    35: "Acoustic Bass Drum", 36: "Bass Drum 1",
    37: "Side Stick", 38: "Acoustic Snare", 39: "Hand Clap",
    40: "Electric Snare", 41: "Floor Tom (merged)",
    42: "Closed Hi-hat", 43: "Pedal Hi-hat", 44: "Open Hi-hat",
    45: "Mid Tom (merged)", 46: "Crash Cymbal (merged)",
    47: "High Tom", 48: "Ride Cymbal (merged)", 49: "Chinese Cymbal",
    50: "Tambourine", 51: "Splash Cymbal", 52: "Cowbell (merged)",
    53: "Vibraslap", 54: "Congas and Timbales", 55: "Shaker",
    56: "Whistle", 57: "Guiro", 58: "Claves",
    59: "Cuica", 60: "Triangle",
}
NAMESPACES = ("gm", "adt_str_custom")


def mapping_sha256() -> str:
    payload = json.dumps(
        [[pitch, GM_TO_VENDOR[pitch]] for pitch in sorted(GM_TO_VENDOR)],
        separators=(",", ":"), ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def validate_mapping() -> None:
    if set(GM_TO_VENDOR) != set(range(35, 82)):
        raise RuntimeError("Pinned GM mapping is incomplete or has out-of-range keys")
    if set(GM_TO_VENDOR.values()) != set(range(35, 61)):
        raise RuntimeError("Pinned ADT_STR 26-class vocabulary no longer matches table")
    if set(VENDOR_CLASS_NAMES) != set(range(35, 61)):
        raise RuntimeError("Missing instrument names for one or more classes")


validate_mapping()


def project_events(
    midi: pretty_midi.PrettyMIDI,
    *,
    source_namespace: Literal["gm", "adt_str_custom"],
) -> list[Event]:
    """Map *copies of event labels* into the 26-class comparison ontology.

    No general-purpose conversion back to GM is possible: multiple GM
    instruments may intentionally share one ADT_STR internal class.
    """
    if source_namespace not in NAMESPACES:
        raise ValueError(f"Unknown drum pitch namespace: {source_namespace!r}")
    result: list[Event] = []
    for event in drum_events(midi):
        if source_namespace == "gm":
            if event.pitch not in GM_TO_VENDOR:
                raise ValueError(
                    f"GM note {event.pitch} has no published ADT_STR ontology mapping; "
                    "refusing to silently drop or guess this drum label"
                )
            label = GM_TO_VENDOR[event.pitch]
        else:
            if event.pitch not in VENDOR_CLASS_NAMES:
                raise ValueError(
                    f"ADT_STR custom note {event.pitch} is outside pinned 26-class "
                    "model output; verify actual tokenizer configuration"
                )
            label = event.pitch
        result.append(Event(pitch=label, start=event.start, end=event.end))
    return sorted(result, key=lambda e: (e.pitch, e.start, e.end))



def require_custom_checkpoint(transcriber) -> dict:
    """Fail closed unless the actual loaded checkpoint emits 26 custom labels.

    Pinning a source training configuration alone is not sufficient evidence
    that the downloaded model checkpoint contains the same tokenizer options.
    """
    tokenizer = getattr(transcriber, "tokenizer", None)
    enabled = getattr(tokenizer, "ADTOF_mapping", None)
    if enabled is not False:
        raise RuntimeError(
            "ADT_STR checkpoint tokenizer is not verified for custom 26-class "
            "output (ADTOF_mapping must be explicitly false); refuse ontology scoring"
        )
    return {
        "ADTOF_mapping": False,
        "verified_from": "loaded_ADTTranscriber.tokenizer",
        "output_namespace": "adt_str_custom",
        "upstream_source_sha": UPSTREAM_SOURCE_SHA,
    }

def evaluate_common_ontology(
    reference: pretty_midi.PrettyMIDI,
    predicted: pretty_midi.PrettyMIDI,
    *,
    prediction_namespace: Literal["gm", "adt_str_custom"],
    tolerance_ms: float = 50.0,
) -> dict:
    if not math.isfinite(tolerance_ms) or not 1 <= tolerance_ms <= 200:
        raise ValueError("tolerance_ms must be 1..200 and finite")
    truth = project_events(reference, source_namespace="gm")
    guess = project_events(predicted, source_namespace=prediction_namespace)
    tol = tolerance_ms / 1000
    pairs = matching(truth, guess, tol, require_offset=False)
    differences = [
        1000 * (guess[p].start - truth[r].start) for r, p in pairs
    ]
    per_class = {}
    for class_id in sorted({e.pitch for e in truth + guess}):
        t = [e for e in truth if e.pitch == class_id]
        p = [e for e in guess if e.pitch == class_id]
        matched = matching(t, p, tol, require_offset=False)
        per_class[str(class_id)] = {
            "class_name": VENDOR_CLASS_NAMES[class_id],
            "reference_count": len(t),
            "predicted_count": len(p),
            **score(len(t), len(p), matched),
        }
    return {
        "ontology_id": ONTOLOGY_ID,
        "source_revision": UPSTREAM_SOURCE_SHA,
        "mapping_sha256": mapping_sha256(),
        "reference_namespace": "gm",
        "prediction_namespace": prediction_namespace,
        "tolerance_ms": tolerance_ms,
        "reference_events": len(truth),
        "predicted_events": len(guess),
        "micro": score(len(truth), len(guess), pairs),
        "per_class": per_class,
        "matched_onset_mae_ms": (
            round(sum(abs(t) for t in differences) / len(differences), 4)
            if differences else None
        ),
        "note": (
            "Same fixed 26-class reduced ontology and one-to-one note-onset matching. "
            "Do NOT present this as exact full-GM pitch accuracy or GM-exported MIDI."
        ),
    }


def summarize_ontology(rows: list[dict]) -> dict:
    """Aggregate per-song results, keeping song macro and event micro separate."""
    if not rows:
        return {"sample_count": 0, "song_count": 0}
    songs: dict[str, Counter] = defaultdict(Counter)
    classes: dict[str, Counter] = defaultdict(Counter)
    counts = Counter()
    for row in rows:
        song = row.get("song_id")
        data = row.get("ontology_scores")
        if not isinstance(song, str) or not song or not isinstance(data, dict):
            raise ValueError("Missing song or ontology score")
        if data.get("ontology_id") != ONTOLOGY_ID or data.get("mapping_sha256") != mapping_sha256():
            raise ValueError("Inconsistent ontology revision in ensemble")
        sample = data["micro"]
        check = Counter()
        for pitch, cls in data["per_class"].items():
            for key in ("tp", "fp", "fn"):
                n = cls[key]
                if type(n) is not int or n < 0:
                    raise ValueError("Invalid per-class note count")
                classes[pitch][key] += n
                check[key] += n
        for key in ("tp", "fp", "fn"):
            n = sample[key]
            if type(n) is not int or n != check[key]:
                raise ValueError("Ontology per-class totals mismatch sample score")
            counts[key] += n
            songs[song][key] += n
    micro = score(counts["tp"] + counts["fn"], counts["tp"] + counts["fp"],
                  [(i, i) for i in range(counts["tp"])])
    song_scores = {
        song: score(v["tp"] + v["fn"], v["tp"] + v["fp"],
                    [(i, i) for i in range(v["tp"])])
        for song, v in sorted(songs.items())
    }
    class_scores = {
        pitch: {"class_name": VENDOR_CLASS_NAMES[int(pitch)],
                **score(v["tp"] + v["fn"], v["tp"] + v["fp"],
                        [(i, i) for i in range(v["tp"])])}
        for pitch, v in sorted(classes.items(), key=lambda t: int(t[0]))
    }
    return {
        "ontology_id": ONTOLOGY_ID,
        "mapping_sha256": mapping_sha256(),
        "sample_count": len(rows),
        "song_count": len(songs),
        "event_micro": micro,
        "song_macro_f1": round(
            sum(v["f1"] for v in song_scores.values()) / len(song_scores), 6
        ),
        "per_song": song_scores,
        "per_class": class_scores,
        "missing_reference_classes": sorted(
            int(p) for p, v in class_scores.items() if v["fn"] and not v["tp"]
        ),
        "not_a_full_GM_pitch_score": True,
    }
