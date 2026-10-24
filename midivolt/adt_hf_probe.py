"""Verify exact upstream ADT_STR model revision before any large download.

Requires huggingface_hub. Never treats public availability as legal clearance.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from huggingface_hub import HfApi

REPO_ID = "Pierfrancesco/adt-str"
VARIANT = "setting-tau-0.8"
REQUIRED = {
    f"{VARIANT}/model.safetensors",
    f"{VARIANT}/adt_config.yaml",
}


def probe_model(revision: str, *, client=None) -> dict:
    if len(revision) != 40 or any(char not in "0123456789abcdef" for char in revision.lower()):
        raise ValueError("revision must be an explicit 40-character commit SHA")
    client = client or HfApi()
    info = client.model_info(REPO_ID, revision=revision, files_metadata=True)
    filenames = sorted(s.rfilename for s in info.siblings)
    missing = sorted(REQUIRED.difference(filenames))
    actual = info.sha
    if actual != revision:
        raise RuntimeError(f"Revision mismatch: requested {revision}, resolved {actual}")
    card = info.card_data
    license_label = getattr(card, "license", None) if card is not None else None
    result = {
        "repo_id": REPO_ID,
        "requested_revision": revision,
        "resolved_revision": actual,
        "variant": VARIANT,
        "required_files": sorted(REQUIRED),
        "missing_files": missing,
        "declared_license": license_label,
        "license_gate": "research_only_not_commercially_cleared",
        "files": [
            {
                "path": sibling.rfilename,
                "size_bytes": sibling.size,
                "blob_id": sibling.blob_id,
                "lfs_sha256": getattr(sibling.lfs, "sha256", None) if sibling.lfs else None,
            }
            for sibling in info.siblings
            if sibling.rfilename in REQUIRED
        ],
    }
    return result


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--revision", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        result = probe_model(args.revision)
    except Exception as exc:
        parser.exit(2, f"MODEL PROBE FAILED: {exc}\n")
    payload = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    print(payload)
    if result["missing_files"]:
        parser.exit(3, "MODEL PROBE BLOCKED: required files not present at pinned revision\n")


if __name__ == "__main__":
    main()
