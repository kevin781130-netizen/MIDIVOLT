"""K12 opt-in Text2midi pre-inference compatibility diagnostic.

Asset inspection and pinned upstream AST checks do not execute upstream
code, unpickle REMI or load any model weights. The separate model Python
runs in offline mode. Optional package imports and CUDA smoke are opt-in.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess

from .composition_acceptance import _trusted_asset
from .environments import _read_managed_environment, verify_environment, venv_python
from .model_runners.text2midi_local import (
    inspect_local_t5, inspect_upstream_text2midi_contract,
)
from .review_engine import _save_new_json


def diagnose_composition_runtime(
    *,
    environment, checkout, checkpoint, checkpoint_sha256,
    vocab, vocab_sha256, t5_dir, output_path,
    confirm_imports: bool = False, cuda_smoke: bool = False,
    require_cuda: bool = False, timeout: float = 90,
) -> dict:
    """Report preflight blockers without claiming pretrained inference passed."""
    if (cuda_smoke or require_cuda) and not confirm_imports:
        raise ValueError("CUDA checks require explicit --confirm-imports.")
    if require_cuda and not cuda_smoke:
        raise ValueError("--require-cuda requires --cuda-smoke for real compute verification.")
    if type(timeout) not in (int, float) or not 10 <= timeout <= 180:
        raise ValueError("Runtime probe timeout must be in 10..180 seconds.")
    output = Path(output_path).expanduser().resolve()
    if output.suffix.lower() != ".json" or not output.parent.is_dir():
        raise ValueError("Doctor report needs a new JSON file in an existing directory.")
    if output.exists() or output.is_symlink():
        raise FileExistsError("Doctor report must not overwrite another file.")

    managed = _read_managed_environment(environment)
    if managed.get("model") != "text2midi" or managed.get("installed") is not True:
        raise ValueError("Doctor requires an installed managed Text2midi environment.")
    env = verify_environment(environment, import_model=False)
    if env.get("model") != "text2midi" or env.get("installed") is not True:
        raise ValueError("Managed environment source and requirements not verified.")
    upstream = Path(checkout).expanduser().resolve(strict=True)
    if upstream != Path(managed["checkout"]).resolve():
        raise ValueError("Pinned upstream checkout path does not match managed environment.")
    source_contract = inspect_upstream_text2midi_contract(upstream)
    weights, digest_weights = _trusted_asset(checkpoint, checkpoint_sha256, "checkpoint")
    remi, digest_remi = _trusted_asset(vocab, vocab_sha256, "vocabulary")
    t5 = inspect_local_t5(t5_dir)
    python = venv_python(Path(environment).expanduser().resolve())
    runner = Path(__file__).parent / "model_runners" / "runtime_probe.py"
    if not python.is_file() or not runner.is_file():
        raise ValueError("Managed model Python or bundled runtime probe missing.")
    if output in (weights, remi, upstream) or output.is_relative_to(Path(t5["directory"])):
        raise ValueError("Doctor output may not replace model assets.")
    cmd = [str(python), "-I", str(runner)]
    if confirm_imports:
        cmd.append("--confirm-imports")
    if cuda_smoke:
        cmd.append("--cuda-smoke")
    offline = os.environ.copy()
    offline.update(
        HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1",
        HF_DATASETS_OFFLINE="1", TOKENIZERS_PARALLELISM="false",
    )
    try:
        completed = subprocess.run(
            cmd, cwd=str(upstream), env=offline, shell=False,
            capture_output=True, text=True, errors="replace",
            timeout=timeout, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("Model runtime compatibility subprocess unavailable/timed out.") from exc
    if completed.returncode:
        raise RuntimeError("Model package/CUDA probe failed in isolated model environment.")
    try:
        probe = json.loads(completed.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError) as exc:
        raise ValueError("Model runtime probe did not emit valid JSON.") from exc
    if not isinstance(probe, dict) or probe.get("model_weights_loaded") is not False:
        raise ValueError("Unexpected runtime probe status.")
    if not isinstance(probe.get("missing_packages"), list) or type(probe.get("python_supported")) is not bool:
        raise ValueError("Incomplete runtime probe output.")

    blockers = []
    if not probe["python_supported"]:
        blockers.append("Model Python must be 3.10 or 3.11.")
    if probe["missing_packages"]:
        blockers.append("Missing model Python dependencies: " +
                        ", ".join(probe["missing_packages"]))
    if confirm_imports and probe.get("third_party_packages_imported") is not True:
        blockers.append("Opt-in runtime package imports have not succeeded.")
    if require_cuda and probe.get("cuda_compute_passed") is not True:
        blockers.append("Requested CUDA computation is not verified.")
    if not confirm_imports:
        blockers.append("Import/API compatibility not tested; rerun with --confirm-imports.")
    ready = not blockers
    report = {
        "schema_version": 1,
        "kind": "midivolt_k12_text2midi_preinference_doctor",
        "upstream_commit": env["commit"],
        "requirements_sha256": env["requirements_sha256"],
        "checkpoint_sha256": digest_weights,
        "vocab_sha256": digest_remi,
        "checkpoint_bytes": weights.stat().st_size,
        "vocab_bytes": remi.stat().st_size,
        "local_t5": t5,
        "upstream_source_contract": source_contract,
        "runtime": probe,
        "require_cuda": require_cuda,
        "compatibility_blockers": blockers,
        "ready_for_inference_attempt": ready,
        "upstream_model_imported": False,
        "checkpoint_deserialized": False,
        "remi_unpickled": False,
        "actual_inference_verified": False,
        "music_quality_verified": False,
        "commercial_release_ready": False,
    }
    _save_new_json(output, report)
    return report
