"""Small, independently launched Text2midi runtime compatibility probe.

Never imports upstream model source, loads model weights, unpickles the REMI
vocabulary, contacts a server or generates MIDI. Package imports and a tiny
CUDA kernel are separate explicitly authorized stages.
"""
from __future__ import annotations

import argparse
import importlib.metadata
import inspect
import json
import platform
import sys
import time

PACKAGES = ("torch", "transformers", "sentencepiece", "numpy", "pretty_midi")


def probe(*, import_packages: bool = False, cuda_smoke: bool = False) -> dict:
    if cuda_smoke and not import_packages:
        raise ValueError("CUDA smoke requires explicitly allowed package imports.")
    versions = {}
    missing = []
    for name in PACKAGES:
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            missing.append(name)
    result = {
        "python": platform.python_version(),
        "python_supported": sys.version_info[:2] in ((3, 10), (3, 11)),
        "packages": versions,
        "missing_packages": missing,
        "package_metadata_checked": True,
        "third_party_packages_imported": False,
        "cuda_compute_tested": False,
        "cuda_compute_passed": False,
        "cuda_available": None,
        "device": None,
        "cuda_smoke_ms": None,
        "model_weights_loaded": False,
        "remi_pickle_loaded": False,
        "upstream_model_imported": False,
        "real_inference_verified": False,
    }
    if not import_packages or missing or not result["python_supported"]:
        return result

    import torch
    from transformers import T5Tokenizer
    if not hasattr(torch, "load") or "weights_only" not in inspect.signature(torch.load).parameters:
        raise RuntimeError("Installed torch.load lacks required weights_only support.")
    if T5Tokenizer is None:
        raise RuntimeError("transformers.T5Tokenizer is unavailable.")
    result["third_party_packages_imported"] = True
    result["torch_version_loaded"] = str(torch.__version__)
    result["cuda_runtime"] = str(torch.version.cuda) if torch.version.cuda else None
    result["cuda_available"] = bool(torch.cuda.is_available())
    if result["cuda_available"]:
        result["device"] = torch.cuda.get_device_name(0)
        major, minor = torch.cuda.get_device_capability(0)
        result["cuda_capability"] = [major, minor]
        result["torch_cuda_arch_list"] = list(torch.cuda.get_arch_list())
        try:
            free, total = torch.cuda.mem_get_info(0)
            result["cuda_free_bytes"] = int(free)
            result["cuda_total_bytes"] = int(total)
        except (RuntimeError, AttributeError):
            result["cuda_free_bytes"] = None
            result["cuda_total_bytes"] = None
        target = "sm_" + str(major) + str(minor)
        result["exact_cuda_arch_in_torch_build"] = target in result["torch_cuda_arch_list"]
    if cuda_smoke:
        if not result["cuda_available"]:
            result["cuda_compute_tested"] = False
            return result
        # Small functional smoke, never a model benchmark. Synchronize so
        # results include actual kernel execution rather than async launch.
        started = time.perf_counter()
        x = torch.ones((128, 128), device="cuda")
        y = x @ x
        torch.cuda.synchronize()
        if not torch.isfinite(y).all().item() or abs(y[0, 0].item() - 128.0) > 0.001:
            raise RuntimeError("CUDA matrix multiplication returned invalid values.")
        result["cuda_compute_tested"] = True
        result["cuda_compute_passed"] = True
        result["cuda_smoke_ms"] = round((time.perf_counter() - started) * 1000, 3)
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="midivolt-model-runtime-probe")
    parser.add_argument("--confirm-imports", action="store_true")
    parser.add_argument("--cuda-smoke", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = probe(import_packages=args.confirm_imports, cuda_smoke=args.cuda_smoke)
    except (RuntimeError, ImportError, ValueError, OSError) as exc:
        print(f"Runtime compatibility probe failed: {type(exc).__name__}: {exc}",
              file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
