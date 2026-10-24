"""Offline, deterministic E-GMD v1.0.0 test-set selection and rights-gated import.

Reads canonical Magenta metadata CSV, never downloads a 90-GB dataset.
First prepare a lightweight selection plan, then resolve actual WAV/MIDI
files with per-file SHA-256 into an unapproved rights-review manifest.
No licensing decisions are silently automated.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path

SOURCE_URL = "https://magenta.withgoogle.com/datasets/e-gmd"
DATASET_VERSION = "e-gmd-v1.0.0"
REQUIRED_COLUMNS = (
    "drummer", "session", "id", "style", "bpm", "beat_type", "split",
    "midi_filename", "audio_filename", "kit_name",
)
VALID_SPLITS = ("test", "validation", "train")
SAFE_COMPONENT = re.compile(r"^[A-Za-z0-9_./ \-()]+$")


def _safe_relative(path: str) -> str:
    if not isinstance(path, str) or not path or not SAFE_COMPONENT.fullmatch(path):
        raise ValueError(f"Unsafe/unsupported E-GMD path: {path!r}")
    parsed = Path(path)
    if parsed.is_absolute() or any(p in (".", "..") for p in parsed.parts):
        raise ValueError(f"Metadata path cannot escape dataset: {path!r}")
    return path.replace("\\", "/")


def read_metadata(csv_path: Path) -> list[dict]:
    with Path(csv_path).open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        missing = set(REQUIRED_COLUMNS).difference(reader.fieldnames or ())
        if missing:
            raise ValueError("E-GMD metadata missing required columns: " + ", ".join(sorted(missing)))
        result: list[dict] = []
        for index, row in enumerate(reader, start=2):
            if not row or not row.get("id"):
                continue
            if row["split"] not in VALID_SPLITS:
                raise ValueError(f"CSV line {index}: invalid original split")
            for field in ("midi_filename", "audio_filename"):
                row[field] = _safe_relative(row[field])
            if not row.get("kit_name") or not row.get("style"):
                raise ValueError(f"CSV line {index}: kit_name/style missing")
            try:
                bpm = float(row["bpm"])
                if not 30 <= bpm <= 400:
                    raise ValueError()
            except (ValueError, TypeError):
                raise ValueError(f"CSV line {index}: invalid bpm")
            result.append(row)
    return result


def _rank(key: str, seed: str) -> str:
    return hashlib.sha256((seed + "|" + key).encode()).hexdigest()


def choose_test_samples(
    metadata: list[dict], *, max_performances: int = 12,
    kits_per_performance: int = 2, seed: str = "midivolt-drum-eval-v1",
) -> list[dict]:
    """Select diverse held-out *performances* then at most K kits each.

    All 43 kit renders of the same underlying performance share source_song_id.
    Use upstream split, never move a training performance to test.
    """
    if max_performances < 1 or kits_per_performance < 1:
        raise ValueError("Selection sizes must be positive")
    # For provenance and split integrity, group ID across all upstream splits.
    splits: dict[str, str] = {}
    by_performance: dict[str, list[dict]] = defaultdict(list)
    for row in metadata:
        performance_id = row["id"]
        if performance_id in splits and splits[performance_id] != row["split"]:
            raise ValueError("E-GMD metadata cross-split leakage for performance " + performance_id)
        splits[performance_id] = row["split"]
        if row["split"] == "test":
            by_performance[performance_id].append(row)

    by_style: dict[str, list[str]] = defaultdict(list)
    for performance_id, rows in by_performance.items():
        styles = {(r["style"].split("/")[0], r["beat_type"]) for r in rows}
        if len(styles) != 1:
            raise ValueError("Inconsistent style/beat_type for performance " + performance_id)
        style, beat_type = next(iter(styles))
        by_style[f"{style}:{beat_type}"].append(performance_id)

    queues = {
        key: sorted(ids, key=lambda sid: (_rank(sid, seed), sid))
        for key, ids in by_style.items()
    }
    selected: list[str] = []
    while len(selected) < max_performances and any(queues.values()):
        for key in sorted(queues):
            if queues[key] and len(selected) < max_performances:
                selected.append(queues[key].pop(0))
    selected_rows = []
    for ident in selected:
        candidates = sorted(by_performance[ident], key=lambda r: (
            _rank(r["kit_name"] + "|" + r["audio_filename"], seed),
            r["audio_filename"],
        ))
        used_kits = set()
        for row in candidates:
            if row["kit_name"] in used_kits:
                continue
            used_kits.add(row["kit_name"])
            selected_rows.append(row)
            if len(used_kits) >= kits_per_performance:
                break
    return selected_rows


def make_plan(rows: list[dict], data_root: Path) -> dict:
    root = Path(data_root).resolve()
    entries = []
    for row in rows:
        wav = root / row["audio_filename"]
        midi = root / row["midi_filename"]
        entries.append({
            "dataset": DATASET_VERSION,
            "performance_id": row["id"],
            "style": row["style"],
            "bpm": float(row["bpm"]),
            "beat_type": row["beat_type"],
            "kit_name": row["kit_name"],
            "audio": row["audio_filename"],
            "midi": row["midi_filename"],
            "has_audio": wav.is_file(),
            "has_midi": midi.is_file(),
        })
    return {
        "schema_version": "1",
        "source_url": SOURCE_URL,
        "dataset": DATASET_VERSION,
        "upstream_split": "test",
        "human_performed": True,
        "audio_domain": "electronic_kit_recording",
        "license_declared_by_upstream": "CC-BY-4.0",
        "license_clearance": "requires manual review per exact asset before execution",
        "performance_count": len({row["id"] for row in rows}),
        "pair_count": len(entries),
        "pairs_with_local_files": sum(x["has_audio"] and x["has_midi"] for x in entries),
        "pairs": entries,
    }


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_review_manifest(rows: list[dict], data_root: Path) -> dict:
    """Materialize only if ALL selected files exist; no selective omission."""
    from midivolt.drum_suite import _within_folder

    root = Path(data_root).resolve()
    samples = []
    for row in rows:
        wav = _within_folder(root, row["audio_filename"])
        midi = _within_folder(root, row["midi_filename"])
        ident = row["id"]
        sample_id = "e_gmd_" + hashlib.sha256(
            (ident + "|" + row["audio_filename"] + "|" + row["kit_name"])
            .encode("utf-8")
        ).hexdigest()[:20]
        samples.append({
            "sample_id": sample_id,
            "source_song_id": "e_gmd_" + ident,
            "performance_id": ident,
            "split": "test",
            "audio_domain": "electronic_kit_recording",
            "human_performed": True,
            "audio_path": row["audio_filename"],
            "reference_midi_path": row["midi_filename"],
            "audio_sha256": _hash_file(wav),
            "midi_sha256": _hash_file(midi),
            "reference_midi_mapping": "roland_td11_to_gm",
            "provenance_url": SOURCE_URL,
            "source_dataset": DATASET_VERSION,
            "style": row["style"],
            "beat_type": row["beat_type"],
            "bpm": float(row["bpm"]),
            "kit_name": row["kit_name"],
            "technique_tags": [],
            "rights": {
                "status": "pending",
                "commercial_benchmark_allowed": False,
                "audio_license": "CC-BY-4.0 (upstream declaration; asset review pending)",
                "midi_license": "CC-BY-4.0 (upstream declaration; asset review pending)",
                "evidence_url": SOURCE_URL,
                "reviewer": "unassigned",
                "attribution": (
                    "Google LLC, Expanded Groove MIDI Dataset v1.0.0, "
                    "CC BY 4.0; Callender, Hawthorne & Engel (2020)."
                ),
            },
        })
    return {
        "schema_version": "1",
        "dataset": DATASET_VERSION,
        "purpose": "Rights review draft; edit pending fields only after genuine review",
        "samples": samples,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--csv", type=Path, required=True, help="official e-gmd-v1.0.0.csv")
    p.add_argument("--data-root", type=Path, required=True, help="extracted dataset root")
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--mode", choices=("plan", "review-manifest"), default="plan")
    p.add_argument("--max-performances", type=int, default=12)
    p.add_argument("--kits-per-performance", type=int, default=2)
    p.add_argument("--seed", default="midivolt-drum-eval-v1")
    args = p.parse_args(argv)
    try:
        rows = choose_test_samples(
            read_metadata(args.csv),
            max_performances=args.max_performances,
            kits_per_performance=args.kits_per_performance,
            seed=args.seed,
        )
        result = (
            make_plan(rows, args.data_root) if args.mode == "plan"
            else build_review_manifest(rows, args.data_root)
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except (OSError, ValueError, RuntimeError) as exc:
        p.exit(1, f"E-GMD import blocked: {exc}\n")
    print(json.dumps({
        "mode": args.mode, "rows": len(rows),
        "output": str(args.output),
        "rights_cleared": False,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
