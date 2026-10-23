#!/usr/bin/env python3
"""Fail-closed validation for MIDIVOLT's audio-to-MIDI dataset manifest.

The inventory mode checks the registry structure.
The commercial mode refuses any dataset without explicit, evidence-backed clearance.
This script validates metadata; it does not provide legal advice or independently verify rights.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

DISPOSITIONS = {
    "conditional_commercial_candidate",
    "research_only_permission_required",
    "blocked_pending_rights",
    "commercially_cleared",
}
REQUIRED_DATASET_FIELDS = (
    "dataset_id",
    "name",
    "instrument_scope",
    "data_kind",
    "official_url",
    "declared_license",
    "disposition",
    "intended_use",
    "rights_review",
)
SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
CLEARANCE_FIELDS = (
    "reviewer",
    "reviewed_at",
    "evidence_url",
    "release_version",
    "downloaded_at",
    "audio_license",
    "annotation_license",
    "attribution",
    "artifact_checksums",
    "permissions",
)


def _is_http_url(value: object) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def validate_manifest(data: object, mode: str = "commercial") -> list[str]:
    """Return validation errors; commercial mode is deliberately fail-closed."""
    errors: list[str] = []
    if mode not in {"inventory", "commercial"}:
        return [f"unsupported validation mode: {mode}"]
    if not isinstance(data, dict):
        return ["manifest root must be a JSON object"]

    datasets = data.get("datasets")
    if not isinstance(datasets, list):
        return ["manifest.datasets must be a list"]

    seen_ids: set[str] = set()
    for index, dataset in enumerate(datasets):
        label = f"datasets[{index}]"
        if not isinstance(dataset, dict):
            errors.append(f"{label} must be an object")
            continue

        for field in REQUIRED_DATASET_FIELDS:
            value = dataset.get(field)
            if value is None or value == "" or value == []:
                errors.append(f"{label}.{field} is required")

        dataset_id = dataset.get("dataset_id")
        if isinstance(dataset_id, str) and dataset_id:
            if dataset_id in seen_ids:
                errors.append(f"{label}.dataset_id duplicates {dataset_id!r}")
            seen_ids.add(dataset_id)

        disposition = dataset.get("disposition")
        if not isinstance(disposition, str) or disposition not in DISPOSITIONS:
            errors.append(
                f"{label}.disposition must be one of: {', '.join(sorted(DISPOSITIONS))}"
            )

        if not _is_http_url(dataset.get("official_url")):
            errors.append(f"{label}.official_url must be an absolute HTTP(S) URL")

        if mode != "commercial":
            continue

        if disposition != "commercially_cleared":
            errors.append(
                f"{label} ({dataset_id or 'unknown dataset'}) is blocked: "
                f"disposition is {disposition!r}, not 'commercially_cleared'"
            )
            continue

        clearance = dataset.get("commercial_clearance")
        if not isinstance(clearance, dict):
            errors.append(f"{label}.commercial_clearance must be an object")
            continue

        if clearance.get("status") != "approved":
            errors.append(f"{label}.commercial_clearance.status must equal 'approved'")

        for field in CLEARANCE_FIELDS:
            value = clearance.get(field)
            if value is None or value == "" or value == [] or value == {}:
                errors.append(f"{label}.commercial_clearance.{field} is required")

        if not _is_http_url(clearance.get("evidence_url")):
            errors.append(
                f"{label}.commercial_clearance.evidence_url must be an absolute HTTP(S) URL"
            )

        permissions = clearance.get("permissions")
        if not isinstance(permissions, dict):
            errors.append(f"{label}.commercial_clearance.permissions must be an object")
        else:
            for permission in ("commercial_use", "benchmark"):
                if permissions.get(permission) is not True:
                    errors.append(
                        f"{label}.commercial_clearance.permissions.{permission} must be true"
                    )

        checksums = clearance.get("artifact_checksums")
        if not isinstance(checksums, list) or not checksums:
            errors.append(
                f"{label}.commercial_clearance.artifact_checksums must be a non-empty list"
            )
        else:
            for checksum_index, item in enumerate(checksums):
                checksum_label = (
                    f"{label}.commercial_clearance.artifact_checksums[{checksum_index}]"
                )
                if not isinstance(item, dict):
                    errors.append(f"{checksum_label} must be an object")
                    continue
                if not isinstance(item.get("path"), str) or not item["path"].strip():
                    errors.append(f"{checksum_label}.path is required")
                if not isinstance(item.get("sha256"), str) or not SHA256_RE.fullmatch(item["sha256"]):
                    errors.append(f"{checksum_label}.sha256 must be 64 hexadecimal characters")

        if not isinstance(clearance.get("reviewer"), str) or not clearance["reviewer"].strip():
            errors.append(f"{label}.commercial_clearance.reviewer must be non-empty")

    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path(__file__).with_name("manifest.json"),
        help="path to manifest.json (default: sibling manifest.json)",
    )
    parser.add_argument(
        "--mode",
        choices=("inventory", "commercial"),
        default="commercial",
        help="inventory checks structure; commercial fails closed unless every dataset is cleared",
    )
    args = parser.parse_args(argv)

    try:
        data = json.loads(args.manifest.read_text(encoding="utf-8"))
    except OSError as exc:
        print(f"ERROR: cannot read manifest {args.manifest}: {exc}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as exc:
        print(f"ERROR: invalid JSON in {args.manifest}: {exc}", file=sys.stderr)
        return 2

    errors = validate_manifest(data, args.mode)
    count = len(data.get("datasets", [])) if isinstance(data, dict) and isinstance(data.get("datasets"), list) else 0

    if errors:
        print(f"FAIL: {len(errors)} validation issue(s); mode={args.mode}; datasets={count}")
        for error in errors:
            print(f"- {error}")
        return 1

    print(f"PASS: mode={args.mode}; datasets={count}")
    if args.mode == "inventory":
        print("NOTE: inventory PASS is not commercial clearance.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
