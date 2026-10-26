"""Cut 29: audit available ORIGINAL metadata before further model scores.

Never accesses WAVs/MIDI/training examples, and does not choose a
model or expose any TEST performances in a research evaluation.
"""
from __future__ import annotations

from collections import Counter
import json
from pathlib import Path

from scripts.egmd_mini_real import get_small_csv
from midivolt.egmd_import import read_metadata
from midivolt.hat_ranker_independent_eval import PREVIOUS_VAL_IDS

CUT28_VAL_IDS = frozenset((
    "drummer1/session2/1", "drummer7/session2/8",
    "drummer5/session2/17", "drummer7/session2/15",
    "drummer1/session2/38", "drummer7/session2/48",
    "drummer1/session2/107", "drummer7/session3/136",
    "drummer7/session3/34", "drummer1/session2/144",
    "drummer7/session2/119", "drummer1/session1/147",
))
CUT28_TRAIN_IDS = frozenset((
    "drummer3/session1/34", "drummer1/session2/90",
    "drummer7/session2/63", "drummer5/session2/9",
    "drummer8/session1/3", "drummer4/session1/7",
    "drummer10/session1/1", "drummer9/session1/21",
    "drummer6/session1/5", "drummer1/session1/81",
    "drummer7/session2/80", "drummer5/session1/10",
    "drummer8/session1/17", "drummer3/session1/33",
    "drummer4/session1/4", "drummer10/session1/10",
    "drummer7/session3/74", "drummer1/session2/171",
    "drummer3/session2/45", "drummer1/session1/12",
    "drummer7/session1/36", "drummer3/session2/39",
    "drummer7/session3/13", "drummer1/session2/145",
))
PREVIOUS_72_VAL_IDS = PREVIOUS_VAL_IDS | CUT28_VAL_IDS


def metadata_audit(rows: list[dict]) -> dict:
    if len(PREVIOUS_72_VAL_IDS) != 72 or len(CUT28_TRAIN_IDS) != 24:
        raise ValueError("Prior study source IDs changed")
    result = {"excluded_validation_ids": sorted(PREVIOUS_72_VAL_IDS),
              "excluded_validation_count": len(PREVIOUS_72_VAL_IDS),
              "previous_train_count": len(CUT28_TRAIN_IDS),
              "bins": {}}
    for ceiling in (60, 90, 120, 180):
        result["bins"][str(ceiling)] = {}
        for split in ("train", "validation"):
            eligible = []
            for r in rows:
                if r.get("split") != split or r.get("kit_name") != "Acoustic Kit":
                    continue
                if split == "validation" and r.get("id") in PREVIOUS_72_VAL_IDS:
                    continue
                try:
                    seconds = float(r.get("duration", ""))
                except (TypeError, ValueError):
                    continue
                if not 0 < seconds <= ceiling:
                    continue
                eligible.append(r)
            unique = {r["id"]: r for r in eligible}
            by_type = Counter(x["beat_type"] for x in unique.values())
            result["bins"][str(ceiling)][split] = {
                "unique_songs": len(unique),
                "beat": by_type.get("beat", 0),
                "fill": by_type.get("fill", 0),
                "drummers": len({x["drummer"] for x in unique.values()}),
                "total_audio_seconds": round(sum(float(x["duration"]) for x in unique.values()), 2),
            }
    return result


if __name__ == "__main__":
    folder = Path("/tmp/midivolt-cut29-metadata")
    folder.mkdir(exist_ok=True, parents=True)
    csv, sha = get_small_csv(folder / "official.csv")
    x = metadata_audit(read_metadata(csv))
    x["official_csv_sha256"] = sha
    p = folder / "remaining_split_capacity.json"
    p.write_text(json.dumps(x, ensure_ascii=False, indent=2)+"\n")
    print(json.dumps({"official_csv_sha256": sha, "bins": x["bins"]}, indent=2))
