"""Fail-closed E-GMD replay lock BEFORE large model inference.

Read the *original* completed six-song GitHub artifact ZIP. Require:
- a matching selection_plan.json byte hash,
- identical ordered metadata-only song selection,
- identical extracted WAV and reference MIDI SHA-256,
- an unchanged, pinned ADT_STR checkpoint and data domain.

No model weights, audio or references are modified. This does not verify
model notes (those require actual replay inference).
"""
from __future__ import annotations

import hashlib
import json
import zipfile
from dataclasses import dataclass
from pathlib import Path


FIELDS = (
    "id", "drummer", "split", "style", "beat_type", "bpm", "duration",
    "kit_name", "audio_filename", "midi_filename",
)
MODEL_KEYS = ("id", "revision", "variant", "sha256", "commercial_status")
DOMAIN = "human_performed_electronic_drumkit_audio_NOT_direct_acoustic_drums"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _item(archive: zipfile.ZipFile, name: str) -> bytes:
    matches = [
        member for member in archive.namelist()
        if member == name or member.endswith("/" + name)
    ]
    if len(matches) != 1:
        raise ValueError(f"Baseline archive requires exactly one {name}")
    payload = archive.read(matches[0])
    if len(payload) > 10 * 1024 * 1024:
        raise ValueError(f"Oversized baseline {name}")
    return payload


@dataclass(frozen=True)
class ReplayLock:
    plan: dict
    report: dict
    archive_sha256: str


def load_replay_lock(path: Path) -> ReplayLock:
    """Require the original two-file ZIP, not an unverified copied JSON."""
    path = Path(path)
    archive_hash = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            archive_hash.update(block)
    with zipfile.ZipFile(path) as archive:
        original_plan_bytes = _item(archive, "selection_plan.json")
        original_report_bytes = _item(archive, "research_metrics.json")
    plan = json.loads(original_plan_bytes)
    report = json.loads(original_report_bytes)
    if not isinstance(plan, dict) or not isinstance(report, dict):
        raise ValueError("Invalid baseline archive JSON objects")
    if _sha(original_plan_bytes) != report.get("selection_plan_sha256"):
        raise ValueError("Original archive's selection plan SHA-256 is inconsistent")
    if report.get("status") != "research_only_completed" or report.get("dataset") != "E-GMD v1.0.0":
        raise ValueError("Baseline is not a completed E-GMD evaluation")
    if report.get("dataset_type") != DOMAIN:
        raise ValueError("Baseline is not the human-performed electronic-kit lane")
    selected = plan.get("selected")
    sources = report.get("sample_provenance")
    if not isinstance(selected, list) or not selected or not isinstance(sources, list):
        raise ValueError("Baseline is missing sample selection/provenance")
    if len(selected) != len(sources):
        raise ValueError("Selected song count differs from source provenance")
    songs = [entry.get("id") for entry in selected]
    if len(set(songs)) != len(songs):
        raise ValueError("Baseline contains repeated source songs")
    for row, source in zip(selected, sources):
        if not isinstance(row, dict) or not isinstance(source, dict):
            raise ValueError("Corrupt baseline row")
        if row.get("id") != source.get("source_song_id"):
            raise ValueError("Baseline order/IDs inconsistent")
        if row.get("audio_filename") != source.get("official_wav_member"):
            raise ValueError("Baseline WAV identity inconsistent")
        if row.get("midi_filename") != source.get("official_midi_member"):
            raise ValueError("Baseline MIDI identity inconsistent")
        if source.get("source_split") != "test" or row.get("split") != "test":
            raise ValueError("Non-Test performance in baseline")
        for key in ("wav_sha256", "midi_sha256"):
            digest = source.get(key)
            if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
                raise ValueError("Baseline missing valid SHA-256: " + key)
    if not isinstance(report.get("model"), dict) or any(
        not report["model"].get(k) for k in MODEL_KEYS
    ):
        raise ValueError("Baseline missing exact model identity")
    return ReplayLock(plan=plan, report=report, archive_sha256=archive_hash.hexdigest())


def verify_selection_lock(lock: ReplayLock, selected_rows: list[dict], metadata_sha256: str) -> dict:
    """Call immediately after choosing rows, BEFORE ZIP Range extraction."""
    expected = lock.plan["selected"]
    if metadata_sha256 != lock.plan.get("metadata_sha256"):
        raise ValueError("Official E-GMD metadata CSV changed: pinned SHA-256 mismatch")
    if len(selected_rows) != len(expected):
        raise ValueError("Selected song count differs from original six-song run")
    for i, (row, known) in enumerate(zip(selected_rows, expected)):
        for field in FIELDS:
            if str(row.get(field)) != str(known.get(field)):
                raise ValueError(f"Song {i} selection drift in {field}")
    return {
        "stage": "metadata_selection_identical",
        "source_song_count": len(expected),
        "selection_ids": [row["id"] for row in selected_rows],
        "metadata_sha256": metadata_sha256,
        "baseline_archive_sha256": lock.archive_sha256,
    }


def verify_audio_lock(lock: ReplayLock, files: list[dict]) -> dict:
    """Call AFTER extraction and before ANY ADT_STR checkpoint download/load."""
    sources = lock.report["sample_provenance"]
    if len(files) != len(sources):
        raise ValueError("Downloaded pair count differs from original")
    for i, (record, known) in enumerate(zip(files, sources)):
        for key, original in (
            ("source_song_id", "source_song_id"),
            ("source_split", "source_split"),
            ("kit_name", "kit_name"),
            ("official_wav_member", "official_wav_member"),
            ("official_midi_member", "official_midi_member"),
            ("wav_sha256", "wav_sha256"),
            ("midi_sha256", "midi_sha256"),
        ):
            if record.get(key) != known.get(original):
                raise ValueError(f"Pair {i}: {key} differs from frozen six-song benchmark")
    return {
        "stage": "identical_wav_and_midi_bytes_confirmed",
        "pair_count": len(files),
        "source_song_ids": [x["source_song_id"] for x in files],
        "baseline_archive_sha256": lock.archive_sha256,
        "does_not_establish_audio_midi_alignment": True,
    }


def verify_model_lock(lock: ReplayLock, model: dict) -> dict:
    if not isinstance(model, dict):
        raise ValueError("Missing pinned ADT_STR model")
    for key in MODEL_KEYS:
        if lock.report["model"].get(key) != model.get(key):
            raise ValueError("Model changed from frozen six-song benchmark: " + key)
    return {
        "stage": "identical_model_checkpoint_identity",
        "model_revision": model["revision"],
        "checkpoint_sha256": model["sha256"],
        "commercial_release_approved": False,
    }
