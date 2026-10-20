"""Opt-in Hugging Face Model Hub: catalog, online discovery, guarded asset fetch.

Never installs Python, imports model code, executes checkpoints, or downloads
without an explicit user command. Hugging Face is a separate optional extra.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha1, sha256
import os
from pathlib import Path
import re
import tempfile
from typing import Any

REVISION = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_GIT_BLOB = re.compile(r"^[0-9a-f]{40}$")


@dataclass(frozen=True)
class ModelEntry:
    key: str
    repo_id: str
    label: str
    task: str
    source_license: str
    expected_model_license: str
    file_allowlist: tuple[str, ...]
    unsafe_files: tuple[str, ...]
    notes: str

    def as_dict(self) -> dict:
        return {
            "key": self.key, "repo_id": self.repo_id, "label": self.label,
            "task": self.task, "source_license": self.source_license,
            "expected_model_license": self.expected_model_license,
            "allowed_assets": list(self.file_allowlist),
            "requires_unsafe_ack": list(self.unsafe_files),
            "notes": self.notes,
        }


CATALOG: dict[str, ModelEntry] = {
    "text2midi": ModelEntry(
        "text2midi", "amaai-lab/text2midi", "AMAAI-Lab Text2midi",
        "Text to multi-track MIDI", "MIT", "apache-2.0",
        ("pytorch_model.bin", "vocab_remi.pkl", "README.md"),
        ("pytorch_model.bin", "vocab_remi.pkl"),
        "A separate Text2midi checkout and local FLAN-T5 tokenizer are required. "
        "The vocabulary is a Python pickle. Review provenance before using.",
    ),
    "anticipation": ModelEntry(
        "anticipation", "stanford-crfm/music-medium-800k",
        "Stanford Anticipatory Music Transformer", "Conditional MIDI accompaniment",
        "Apache-2.0", "apache-2.0",
        ("config.json", "pytorch_model.bin", "README.md"),
        ("pytorch_model.bin",),
        "A separately installed anticipation Python environment is required. "
        "Large PyTorch BIN may contain pickle objects; use trusted weights only.",
    ),
}


class ModelHubError(RuntimeError):
    """Discovery, verification or provisioning failed safely."""


def catalog(query: str | None = None) -> list[dict]:
    needle = (query or "").strip().casefold()
    return [
        item.as_dict() for item in CATALOG.values()
        if not needle or needle in (" ".join((item.key, item.label, item.task, item.repo_id))).casefold()
    ]


def _sdk_api(api=None):
    if api is not None:
        return api
    try:
        from huggingface_hub import HfApi
    except ImportError as exc:
        raise ModelHubError(
            'Online Model Hub requires: python -m pip install -e ".[hub]"'
        ) from exc
    return HfApi(token=False)


def _card_license(info: Any) -> str:
    card = getattr(info, "card_data", None)
    value = card.get("license") if isinstance(card, dict) else getattr(card, "license", None)
    return value.casefold() if isinstance(value, str) else "unknown"


def _remote_files(info: Any) -> list[dict]:
    entries: list[dict] = []
    for file in getattr(info, "siblings", None) or []:
        filename = getattr(file, "rfilename", None)
        if not isinstance(filename, str):
            continue
        lfs = getattr(file, "lfs", None) or {}
        digest = lfs.get("sha256") if isinstance(lfs, dict) else getattr(lfs, "sha256", None)
        blob = getattr(file, "blob_id", None)
        size = getattr(file, "size", None)
        if not isinstance(size, int) or size < 0:
            size = lfs.get("size") if isinstance(lfs, dict) else getattr(lfs, "size", None)
        entries.append({
            "filename": filename,
            "bytes": size if isinstance(size, int) and size >= 0 else None,
            "sha256": digest if isinstance(digest, str) and _SHA256.fullmatch(digest) else None,
            "git_blob_sha1": blob if isinstance(blob, str) and _GIT_BLOB.fullmatch(blob) else None,
        })
    return entries


def inspect_model(key: str, *, online: bool = False, api=None) -> dict:
    """Offline catalog by default; online fetch is opt-in and read-only."""
    if key not in CATALOG:
        raise ValueError(f"Unknown curated model: {key!r}")
    entry = CATALOG[key]
    result = entry.as_dict()
    result["metadata_source"] = "offline_catalog"
    if not online:
        result["license_verified_online"] = False
        result["revision"] = None
        return result
    try:
        info = _sdk_api(api).model_info(
            entry.repo_id, files_metadata=True
        )
    except Exception as exc:
        raise ModelHubError(f"Cannot inspect public model {entry.repo_id}: {exc}") from exc
    license_name = _card_license(info)
    revision = getattr(info, "sha", None)
    if not isinstance(revision, str) or not REVISION.fullmatch(revision):
        raise ModelHubError("Hugging Face returned no valid immutable commit SHA")
    available = _remote_files(info)
    result.update(
        metadata_source="huggingface_live",
        revision=revision,
        remote_license=license_name,
        license_verified_online=(license_name == entry.expected_model_license),
        available_assets=[
            info for info in available if info["filename"] in entry.file_allowlist
        ],
        missing_assets=[
            name for name in entry.file_allowlist
            if name not in {v["filename"] for v in available}
        ],
    )
    return result


def search_models(query: str, *, online: bool = False, limit: int = 10, api=None) -> dict:
    """Search curated models without network; opt-in to HF wide discovery."""
    if not isinstance(query, str) or not query.strip() or len(query) > 120:
        raise ValueError("Search query must be 1..120 characters")
    if not isinstance(limit, int) or not 1 <= limit <= 20:
        raise ValueError("limit must be 1..20")
    result = {"query": query, "curated": catalog(query), "remote": [],
              "network_used": bool(online)}
    if not online:
        return result
    try:
        candidates = _sdk_api(api).list_models(search=query, limit=limit, full=True)
        for item in candidates:
            ident = getattr(item, "id", None)
            if not isinstance(ident, str):
                continue
            result["remote"].append({
                "repo_id": ident,
                "sha": getattr(item, "sha", None),
                "license": _card_license(item),
                "task": getattr(item, "pipeline_tag", None),
                "curated": ident in (v.repo_id for v in CATALOG.values()),
                "download_supported": False if ident not in (
                    v.repo_id for v in CATALOG.values()) else True,
            })
    except Exception as exc:
        raise ModelHubError(f"Model Hub search failed: {exc}") from exc
    return result


def _hashes(path: Path) -> tuple[str, str]:
    sha256_hash, sha1_hash = sha256(), sha1()
    length = path.stat().st_size
    sha1_hash.update(f"blob {length}\0".encode("ascii"))
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            sha256_hash.update(chunk)
            sha1_hash.update(chunk)
    return sha256_hash.hexdigest(), sha1_hash.hexdigest()


def download_asset(
    key: str, filename: str, revision: str, destination: str | Path, *,
    confirm: bool = False, accept_license: str | None = None,
    allow_unsafe_format: bool = False, max_bytes: int = 2_000_000_000,
    api=None, downloader=None,
) -> dict:
    """Download only a reviewed *single* asset from a pinned model commit.

    Authenticates by remote LFS SHA256 (or Git blob SHA1 for small files).
    Stage in the destination filesystem then publish using atomic hard link;
    existing assets cannot be overwritten by races.
    """
    if key not in CATALOG:
        raise ValueError("Download is restricted to curated models")
    entry = CATALOG[key]
    if filename not in entry.file_allowlist:
        raise ValueError("File is not in the model's explicit download allowlist")
    if not isinstance(revision, str) or not REVISION.fullmatch(revision):
        raise ValueError("Pin an exact 40-character lowercase commit SHA from inspect --online")
    if not confirm:
        raise PermissionError("Download requires --confirm-download")
    if not isinstance(accept_license, str) or accept_license.casefold() != entry.expected_model_license:
        raise PermissionError(f"Explicitly accept model license: {entry.expected_model_license}")
    if filename in entry.unsafe_files and not allow_unsafe_format:
        raise PermissionError(
            "Model BIN/PKL may contain executable pickle data; "
            "requires --allow-unsafe-format from a trusted source"
        )
    if type(max_bytes) is not int or not 1 <= max_bytes <= 8_000_000_000:
        raise ValueError("max_bytes must be in 1..8_000_000_000")
    dest = Path(destination).expanduser()
    if dest.is_symlink() or not dest.is_dir():
        raise ValueError("Destination must be an existing, non-symlink directory")
    dest = dest.resolve()
    final = dest / filename
    if final.is_symlink() or final.exists():
        raise FileExistsError(f"Model asset already exists: {final}")
    try:
        info = _sdk_api(api).model_info(
            entry.repo_id, revision=revision, files_metadata=True
        )
    except Exception as exc:
        raise ModelHubError(f"Cannot verify model revision: {exc}") from exc
    if getattr(info, "sha", None) != revision:
        raise ModelHubError("Remote model revision did not match pinned commit")
    license_name = _card_license(info)
    if license_name != entry.expected_model_license:
        raise ModelHubError(f"Model license changed or unavailable ({license_name})")
    available = {v["filename"]: v for v in _remote_files(info)}
    target = available.get(filename)
    if target is None:
        raise ModelHubError("Selected asset not found in verified commit")
    size = target["bytes"]
    if size is None or size > max_bytes:
        raise ModelHubError(f"Unknown or excessive asset size: {size}")
    if not target["sha256"] and not target["git_blob_sha1"]:
        raise ModelHubError("Asset has no verifiable SHA256 or Git blob digest")
    if downloader is None:
        try:
            from huggingface_hub import hf_hub_download
        except ImportError as exc:
            raise ModelHubError('Install optional hub dependency: pip install -e ".[hub]"') from exc
        downloader = hf_hub_download
    with tempfile.TemporaryDirectory(prefix=".midivolt-hub-", dir=dest) as temporary:
        try:
            retrieved = Path(downloader(
                repo_id=entry.repo_id,
                filename=filename,
                revision=revision,
                local_dir=temporary,
                token=False,
            )).resolve(strict=True)
        except Exception as exc:
            raise ModelHubError(f"Asset download failed: {exc}") from exc
        # Download library must not redirect file access outside staging.
        if retrieved != Path(temporary).resolve() / filename:
            raise ModelHubError("Downloader returned an unexpected destination")
        if retrieved.stat().st_size != size:
            raise ModelHubError("Downloaded size differs from remote metadata")
        digest256, digest_git = _hashes(retrieved)
        # Git blob IDs for LFS files describe pointer blobs, not downloaded
        # payloads; verify LFS SHA256 first, git object SHA1 only otherwise.
        if target["sha256"]:
            checksum_ok = target["sha256"] == digest256
        else:
            checksum_ok = target["git_blob_sha1"] == digest_git
        if not checksum_ok:
            raise ModelHubError("Checksum mismatch: refusing to publish asset")
        try:
            os.link(retrieved, final)
        except FileExistsError as exc:
            raise FileExistsError(f"Asset appeared during download: {final}") from exc
    return {
        "model": key, "repo_id": entry.repo_id,
        "file": filename, "path": str(final), "bytes": size,
        "sha256": digest256, "revision": revision, "license": license_name,
        "executed": False, "installed_dependencies": False,
    }


def doctor(key: str, *, python: str | None = None,
           checkout: str | None = None, checkpoint: str | None = None,
           vocab: str | None = None, t5_dir: str | None = None) -> dict:
    """Pure filesystem checks. Does not run a provided interpreter or code."""
    if key not in CATALOG:
        raise ValueError("Unknown model")
    def check(path, kind, relative=None):
        if not path:
            return {"path": None, "ok": False, "detail": "not configured"}
        p = Path(path).expanduser()
        full = p / relative if relative else p
        valid = full.is_file() if kind == "file" else full.is_dir()
        return {"path": str(full), "ok": valid, "detail": kind}
    paths = {
        "python": check(python, "file"),
        "source_checkout": check(checkout, "file",
                                 "model/transformer_model.py" if key == "text2midi"
                                 else "anticipation/sample.py"),
    }
    if key == "text2midi":
        paths.update({
            "checkpoint": check(checkpoint, "file"),
            "vocab_pickle": check(vocab, "file"),
            "flan_t5_tokenizer": check(t5_dir, "dir"),
        })
    else:
        paths.update({
            "model_config": check(checkpoint, "file", "config.json"),
            "model_weights": {
                "path": checkpoint,
                "ok": bool(checkpoint and any(
                    (Path(checkpoint) / f).is_file()
                    for f in ("model.safetensors", "pytorch_model.bin")
                )),
                "detail": "model.safetensors or pytorch_model.bin",
            },
        })
    return {
        "model": key, "ready_for_runtime_smoke": all(x["ok"] for x in paths.values()),
        "checks": paths,
        "runtime_inference_verified": False,
    }
