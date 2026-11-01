"""Restore exact MIDIVOLT source from six offline UTF-8 GitHub snapshot parts.

Verifies Git blob SHA-1 and manifest paths before writing anything. Does not
execute untrusted source, access a network, install dependencies or run CI.
"""
from __future__ import annotations

import argparse
from hashlib import sha1
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sys
import tempfile

ROOT_FILES = {"pyproject.toml", "README.md", "LICENSE", "THIRD_PARTY_NOTICES.md"}


class SnapshotError(ValueError):
    pass


def git_blob_sha(data: bytes) -> str:
    return sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()


def validate_relpath(path: str) -> bool:
    if not isinstance(path, str) or not path or "\\" in path or "\0" in path:
        return False
    parts = PurePosixPath(path).parts
    if path.startswith("/") or "." in parts or ".." in parts or "//" in path:
        return False
    return path in ROOT_FILES or (len(parts) >= 3 and parts[:2] == ("src", "midivolt") and path.endswith(".py"))


def load_snapshot(root: Path) -> tuple[dict, list[tuple[str, bytes]]]:
    manifest_path = root / "source_transport/MANIFEST.json"
    if not manifest_path.is_file() or manifest_path.is_symlink():
        raise SnapshotError("Missing safe snapshot manifest")
    try:
        manifest = json.loads(manifest_path.read_text("utf-8"))
    except (OSError, ValueError, UnicodeError) as exc:
        raise SnapshotError("Malformed manifest") from exc
    if manifest.get("format") != "midivolt-offline-source-snapshot-v1":
        raise SnapshotError("Unexpected snapshot format")
    chunks = manifest.get("chunks")
    expected = manifest.get("files")
    if not isinstance(chunks, list) or len(chunks) != 6 or not isinstance(expected, list) or len(expected) != 40:
        raise SnapshotError("Unexpected chunk or file count")
    if manifest.get("source_blob_count") != 40 or manifest.get("package_module_count") != 36:
        raise SnapshotError("Unexpected source counts")
    if len({item.get("path") for item in expected}) != 40:
        raise SnapshotError("Duplicate source paths")
    file_map = {}
    for i, chunk in enumerate(chunks):
        expected_path = "source_transport/part-" + str(i).zfill(2) + ".json"
        if chunk.get("path") != expected_path:
            raise SnapshotError("Unexpected source chunk path")
        src = root / expected_path
        if not src.is_file() or src.is_symlink():
            raise SnapshotError("Missing/unsafe source chunk")
        raw = src.read_bytes()
        if git_blob_sha(raw) != chunk.get("git_blob_sha"):
            raise SnapshotError("Git SHA mismatch in source chunk")
        try:
            batch = json.loads(raw)
        except (UnicodeError, ValueError) as exc:
            raise SnapshotError("Malformed source chunk") from exc
        if batch.get("source_tree") != manifest.get("source_commit"):
            raise SnapshotError("Source snapshot commit mismatch")
        files = batch.get("files")
        if not isinstance(files, list) or len(files) != chunk.get("files"):
            raise SnapshotError("Source chunk count mismatch")
        for f in files:
            if not isinstance(f, dict):
                raise SnapshotError("Malformed source entry")
            name, declared_sha, text = f.get("path"), f.get("sha"), f.get("content")
            if not validate_relpath(name) or not isinstance(text, str):
                raise SnapshotError("Unsafe source file content/path")
            if name in file_map:
                raise SnapshotError("Repeated source path")
            data = text.encode("utf-8")
            if git_blob_sha(data) != declared_sha:
                raise SnapshotError("Git SHA mismatch for source module")
            file_map[name] = (data, declared_sha, i)
    if set(file_map) != {x.get("path") for x in expected}:
        raise SnapshotError("File inventory mismatch")
    for record in expected:
        entry = file_map[record["path"]]
        if entry[1] != record.get("git_blob_sha") or entry[2] != record.get("chunk"):
            raise SnapshotError("Source manifest SHA mismatch")
    modules = [p for p in file_map if p.startswith("src/midivolt/") and p.endswith(".py")]
    if len(modules) != 36 or not ROOT_FILES.issubset(file_map):
        raise SnapshotError("Missing required product source")
    return manifest, [(name, file_map[name][0]) for name in sorted(file_map)]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    p.add_argument("--destination", type=Path)
    p.add_argument("--verify-only", action="store_true")
    args = p.parse_args(argv)
    try:
        manifest, files = load_snapshot(args.root)
        if args.verify_only:
            print(json.dumps({"status": "PASS_SNAPSHOT_VERIFIED_NOT_INSTALLED", "files": len(files), "commit": manifest["source_commit"]}))
            return 0
        if not args.destination:
            raise SnapshotError("--destination required unless --verify-only")
        dest = args.destination.absolute()
        if dest.exists() or dest.is_symlink():
            raise SnapshotError("Destination exists; refuse overwrite")
        if not dest.parent.is_dir() or dest.parent.is_symlink():
            raise SnapshotError("Unsafe destination parent")
        stage = Path(tempfile.mkdtemp(prefix=".midivolt-staged-", dir=dest.parent))
        try:
            for name, data in files:
                target = stage.joinpath(*PurePosixPath(name).parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
            if dest.exists():
                raise SnapshotError("Destination appeared during restore")
            os.rename(stage, dest)
        finally:
            if stage.exists():
                shutil.rmtree(stage)
        print(json.dumps({"status": "PASS_SOURCE_RESTORED_NOT_INSTALLED", "files": len(files), "destination": str(dest)}))
        return 0
    except (SnapshotError, OSError, UnicodeError, KeyError, TypeError) as exc:
        print(json.dumps({"status": "FAIL_SNAPSHOT", "error": str(exc)}))
        return 2


if __name__ == "__main__":
    sys.exit(main())

