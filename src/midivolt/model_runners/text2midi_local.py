"""Offline FLAN-T5 encoder + tokenizer preflight, without loading weights.

The approved upstream Text2midi Transformer internally requests the literal
'google/flan-t5-base'. MIDIVOLT redirects *only this known request* to the
explicitly provisioned local directory. No network or upstream edits.
"""
from __future__ import annotations

import ast
from contextlib import contextmanager
import json
from pathlib import Path
from unittest.mock import patch

_ENCODERS = ("model.safetensors", "model.safetensors.index.json",
             "pytorch_model.bin", "pytorch_model.bin.index.json")
_MAX_INDEX = 4 * 1024 * 1024


def inspect_local_t5(directory) -> dict:
    folder = Path(directory).expanduser()
    if folder.is_symlink() or not folder.is_dir():
        raise ValueError("T5 assets must be a local non-symlink directory.")
    folder = folder.resolve(strict=True)
    for required in ("tokenizer_config.json", "config.json"):
        file = folder / required
        if not file.is_file() or file.is_symlink():
            raise ValueError(f"Local T5 tokenizer/encoder missing {required}.")
        if file.stat().st_size > _MAX_INDEX:
            raise ValueError(f"T5 metadata file oversized: {required}.")
    try:
        config = json.loads((folder / "config.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise ValueError("T5 encoder config.json is invalid JSON.") from exc
    if not isinstance(config, dict) or config.get("model_type") != "t5":
        raise ValueError("T5 encoder config.json must declare model_type=t5.")
    selected = next((folder / name for name in _ENCODERS if (folder / name).is_file()), None)
    if selected is None:
        raise ValueError("Local T5 encoder weights missing (safetensors or bin).")
    if selected.is_symlink() or selected.stat().st_size <= 0:
        raise ValueError("T5 encoder weights must be nonempty non-symlink files.")
    files = [selected]
    if selected.suffix == ".json":
        if selected.stat().st_size > _MAX_INDEX:
            raise ValueError("T5 encoder shard index exceeds size budget.")
        try:
            index = json.loads(selected.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValueError) as exc:
            raise ValueError("Invalid T5 encoder shard manifest.") from exc
        weights = index.get("weight_map") if isinstance(index, dict) else None
        if not isinstance(weights, dict) or not weights or len(weights) > 150000:
            raise ValueError("T5 encoder index has no usable weight_map.")
        shards = set(weights.values())
        if any(not isinstance(x, str) or not x or x != Path(x).name
               or "/" in x or "\\" in x or
               not x.endswith(".safetensors" if selected.name.startswith("model.") else ".bin")
               for x in shards):
            raise ValueError("T5 encoder shard index contains unsafe filenames.")
        for name in sorted(shards):
            file = folder / name
            if not file.is_file() or file.is_symlink() or file.stat().st_size <= 0:
                raise ValueError("T5 encoder shard missing or unsafe: " + name)
            files.append(file)
    return {
        "directory": str(folder),
        "encoder_format": "safetensors" if selected.name.startswith("model.") else "pytorch_bin",
        "encoder_files": [x.name for x in files],
        "encoder_total_bytes": sum(x.stat().st_size for x in files),
        "tokenizer_metadata_present": True,
        "encoder_weights_present": True,
        "weight_contents_or_signature_validated": False,
    }


def inspect_upstream_text2midi_contract(checkout) -> dict:
    file = Path(checkout) / "model" / "transformer_model.py"
    if file.is_symlink() or not file.is_file() or file.stat().st_size > 3_000_000:
        raise ValueError("Upstream transformer source missing/oversized/symlink.")
    try:
        tree = ast.parse(file.read_text(encoding="utf-8"), filename=str(file))
    except (OSError, UnicodeError, SyntaxError) as exc:
        raise ValueError("Cannot statically parse pinned Text2midi source.") from exc
    found = next((n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "Transformer"), None)
    if found is None:
        raise ValueError("Pinned source has no Transformer class.")
    initializer = next((n for n in found.body if isinstance(n, ast.FunctionDef) and n.name == "__init__"), None)
    generator = next((n for n in found.body if isinstance(n, ast.FunctionDef) and n.name == "generate"), None)
    if initializer is None or generator is None:
        raise ValueError("Pinned Transformer lacks constructor or generate().")
    if "device" not in [arg.arg for arg in (*initializer.args.args, *initializer.args.kwonlyargs)]:
        raise ValueError("Pinned Transformer lacks expected device keyword.")
    local_encoder_request = any(
        isinstance(call, ast.Call) and
        isinstance(call.func, ast.Attribute) and
        call.func.attr == "from_pretrained" and
        call.args and isinstance(call.args[0], ast.Constant) and
        call.args[0].value == "google/flan-t5-base"
        for call in ast.walk(initializer)
    )
    if not local_encoder_request:
        raise ValueError("Pinned upstream encoder loading contract differs; review manually.")
    return {
        "static_source_contract_verified": True,
        "constructor_device_supported": True,
        "generator_method_present": True,
        "known_flan_t5_base_encoder_request": True,
        "upstream_code_executed": False,
    }


@contextmanager
def redirect_known_t5_encoder(T5EncoderModel, local_dir):
    """Patch T5EncoderModel only around trusted upstream model construction."""
    data = inspect_local_t5(local_dir)
    original = T5EncoderModel.from_pretrained

    def load_local(name, *args, **kwargs):
        if name != "google/flan-t5-base":
            raise RuntimeError("Unexpected upstream encoder identifier; refusing network resolution.")
        if args:
            raise RuntimeError("Unexpected T5 encoder positional arguments.")
        kwargs["local_files_only"] = True
        return original(data["directory"], **kwargs)

    with patch.object(T5EncoderModel, "from_pretrained", side_effect=load_local):
        yield
