"""Metadata-only, deterministic E-GMD diversity selection.

Use only official TEST metadata. NO reference MIDI or model predictions enter
sample selection, preventing score-driven test-set cherry-picking.
"""
from __future__ import annotations

import hashlib
import math
from collections import Counter


def _hash_choice(seed: str, identifier: str) -> str:
    return hashlib.sha256((seed + "|" + identifier).encode("utf-8")).hexdigest()


def select_diverse_test_rows(
    metadata: list[dict],
    *,
    count: int = 6,
    min_duration: float = 8.0,
    max_duration: float = 35.0,
    min_drummers: int = 3,
    kit: str = "Acoustic Kit",
    seed: str = "midivolt-e-gmd-heldout-diverse-v1",
) -> list[dict]:
    """Select distinct official Test performances before running any model.

    Encourages unique drummers, beat/fill diversity, genres, tempos, and
    non-trivial duration. Requires a minimum *actual* performer count;
    never silently falls back to many clips from one drummer.
    """
    if not 1 <= count <= 24:
        raise ValueError("count must be between 1 and 24")
    if not (1 <= min_drummers <= count):
        raise ValueError("min_drummers must be between 1 and count")
    if not (0 < min_duration <= max_duration <= 180):
        raise ValueError("Specify valid minimum/maximum duration in seconds")

    candidates: dict[str, dict] = {}
    for row in metadata:
        if row.get("split") != "test" or row.get("kit_name") != kit:
            continue
        try:
            duration = float(row.get("duration", ""))
            bpm = float(row.get("bpm", ""))
        except (TypeError, ValueError):
            continue
        if not (math.isfinite(duration) and min_duration <= duration <= max_duration):
            continue
        if not (math.isfinite(bpm) and 30 <= bpm <= 400):
            continue
        ident = row.get("id")
        drummer = row.get("drummer")
        beat_type = row.get("beat_type")
        style = row.get("style")
        if not all(isinstance(x, str) and x.strip() for x in (ident, drummer, beat_type, style)):
            continue
        if beat_type not in ("beat", "fill"):
            continue
        existing = candidates.get(ident)
        if existing is not None:
            if existing["audio_filename"] != row["audio_filename"]:
                raise ValueError("Duplicate Test performance ID with different WAV: " + ident)
            continue
        candidates[ident] = row

    if len(candidates) < count:
        raise ValueError(
            f"Only {len(candidates)} official Test performances satisfy duration and kit filters; "
            f"requested {count}. No train/validation substitutions allowed."
        )
    drummers = {r["drummer"] for r in candidates.values()}
    if len(drummers) < min_drummers:
        raise ValueError(
            f"Only {len(drummers)} distinct eligible drummers; at least {min_drummers} required. "
            "Increase duration window or reduce the explicit diversity requirement."
        )

    pool = list(candidates.values())
    selected: list[dict] = []
    used_drummers: Counter[str] = Counter()
    used_types: Counter[str] = Counter()
    used_styles: Counter[str] = Counter()
    used_tempo_buckets: Counter[str] = Counter()

    for position in range(count):
        slots = count - position
        missing_drummers = max(0, min_drummers - len(used_drummers))
        remaining_new_drummers = {r["drummer"] for r in pool if r["drummer"] not in used_drummers}
        if len(remaining_new_drummers) < missing_drummers:
            raise ValueError("Diversity selection could not satisfy minimum distinct drummers.")
        # A sample from a new drummer is mandatory when the remaining slots
        # equal the remaining distinct-drummer requirement.
        require_new_drummer = bool(missing_drummers and slots <= missing_drummers)

        def rank(row: dict) -> tuple:
            novelty_drummer = int(row["drummer"] not in used_drummers)
            novelty_type = int(row["beat_type"] not in used_types)
            primary_style = row["style"].split("/")[0]
            novelty_style = int(primary_style not in used_styles)
            bpm = float(row["bpm"])
            tempo_bucket = "slow" if bpm < 90 else "medium" if bpm < 135 else "fast"
            novelty_tempo = int(tempo_bucket not in used_tempo_buckets)
            duration = float(row["duration"])
            # Deterministic metadata-only diversity objective. Novel styles
            # and beat/fill types matter more than selecting long outliers.
            return (
                -novelty_drummer * 100
                -novelty_type * 75
                -novelty_style * 40
                -novelty_tempo * 20
                + used_drummers[row["drummer"]] * 15
                + used_types[row["beat_type"]] * 9
                + used_styles[primary_style] * 5,
                abs(duration - (min_duration + max_duration) / 2),
                _hash_choice(seed, row["id"]),
            )

        choices = [
            r for r in pool
            if not require_new_drummer or r["drummer"] not in used_drummers
        ]
        chosen = min(choices, key=rank)
        selected.append(chosen)
        pool.remove(chosen)
        used_drummers[chosen["drummer"]] += 1
        used_types[chosen["beat_type"]] += 1
        used_styles[chosen["style"].split("/")[0]] += 1
        bpm = float(chosen["bpm"])
        used_tempo_buckets["slow" if bpm < 90 else "medium" if bpm < 135 else "fast"] += 1

    if len(used_drummers) < min_drummers:
        raise RuntimeError("Bug: minimum drummer diversity not achieved")
    return selected



def select_mixed_test_rows(
    metadata: list[dict],
    *,
    count: int = 6,
    short_fill_count: int = 2,
    min_long_duration: float = 8.0,
    max_long_duration: float = 35.0,
    min_drummers: int = 3,
    kit: str = "Acoustic Kit",
    seed: str = "midivolt-e-gmd-heldout-diverse-v1",
) -> list[dict]:
    """Four long beat/groove excerpts plus two short fills by default.

    Prevents a selection window that inadvertently drops all fills from
    the test split. Each stratum is chosen without observing note labels,
    waveform content, or any model predictions.
    """
    if not 0 <= short_fill_count < count:
        raise ValueError("short_fill_count must be between zero and count-1")
    long_count = count - short_fill_count
    if min_drummers > long_count:
        raise ValueError("min_drummers must fit within long excerpts")
    long_rows = [r for r in metadata if r.get("beat_type") == "beat"]
    chosen_long = select_diverse_test_rows(
        long_rows, count=long_count,
        min_duration=min_long_duration, max_duration=max_long_duration,
        min_drummers=min_drummers, kit=kit, seed=seed + "|long",
    )
    if not short_fill_count:
        return chosen_long
    short_fill_rows = [r for r in metadata if r.get("beat_type") == "fill"]
    chosen_fills = select_diverse_test_rows(
        short_fill_rows, count=short_fill_count,
        min_duration=1.0, max_duration=7.0,
        min_drummers=1, kit=kit, seed=seed + "|short-fill",
    )
    all_rows = chosen_long + chosen_fills
    ids = [x["id"] for x in all_rows]
    if len(ids) != len(set(ids)):
        raise RuntimeError("Duplicate E-GMD performance across strata")
    if len({x["drummer"] for x in all_rows}) < min_drummers:
        raise RuntimeError("Selection lacks minimum independent drummer coverage")
    return all_rows


def selection_summary(rows: list[dict]) -> dict:
    if not rows:
        raise ValueError("Cannot describe an empty performance selection.")
    duration = [float(x["duration"]) for x in rows]
    return {
        "performance_count": len(rows),
        "drummer_count": len({x["drummer"] for x in rows}),
        "unique_song_ids": len({x["id"] for x in rows}),
        "genres": dict(sorted(Counter(x["style"].split("/")[0] for x in rows).items())),
        "beat_types": dict(sorted(Counter(x["beat_type"] for x in rows).items())),
        "tempo_bpm_min_max": [min(float(x["bpm"]) for x in rows), max(float(x["bpm"]) for x in rows)],
        "duration_seconds_min_max": [round(min(duration), 3), round(max(duration), 3)],
        "total_duration_seconds": round(sum(duration), 3),
        "kit_names": sorted({x["kit_name"] for x in rows}),
        "original_split": sorted({x["split"] for x in rows}),
        "selection_policy": "metadata_only_before_inference_no_test_tuning",
    }
