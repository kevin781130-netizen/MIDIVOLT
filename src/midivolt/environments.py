"""MIDIVOLT model-specific venv lifecycle. Never silently downloads software.

An upstream checkout is untrusted code. Creating venvs is offline; installing
requirements or importing model modules requires explicit user opt-in.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

SUPPORTED = frozenset(("text2midi", "anticipation"))
COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
MARKER = ".midivolt-model-env.json"

class EnvironmentError(RuntimeError):
    """Invalid input, incompatible environment or failed process."""

@dataclass(frozen=True)
class EnvironmentPlan:
    model: str
    checkout: Path
    expected_commit: str
    requirements_sha256: str
    interpreter: Path
    python_version: str
    destination: Path

    def as_dict(self):
        return {
            "model": self.model,
            "checkout": str(self.checkout),
            "expected_commit": self.expected_commit,
            "requirements_sha256": self.requirements_sha256,
            "base_python": str(self.interpreter),
            "base_python_version": self.python_version,
            "environment": str(self.destination),
            "venv_python": str(venv_python(self.destination)),
            "network_used": False,
        }

def _run(argv: list[str], *, cwd=None, timeout=180, env=None):
    try:
        result = subprocess.run(argv, cwd=cwd, env=env, shell=False,
                                capture_output=True, text=True, errors="replace",
                                timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise EnvironmentError(f"Subprocess unavailable or timed out: {argv[0]}") from exc
    if result.returncode != 0:
        raise EnvironmentError(
            f"Subprocess failed ({result.returncode}): {(result.stderr or result.stdout)[-1600:]}"
        )
    return result.stdout.strip()

def venv_python(venv: Path) -> Path:
    return venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")

def _requirements(root: Path) -> Path:
    path = root / "requirements.txt"
    if not path.is_file() or path.is_symlink():
        raise ValueError("Expected an ordinary requirements.txt in upstream checkout")
    return path

def _digest(file: Path) -> str:
    h = sha256()
    with file.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

def _inspect_checkout(model: str, checkout: Path, expected_commit: str) -> None:
    if not COMMIT_PATTERN.fullmatch(expected_commit):
        raise ValueError("Expected commit must be a lowercase 40-character SHA")
    src = ("model/transformer_model.py" if model == "text2midi" else
           "anticipation/sample.py")
    if not (checkout / src).is_file():
        raise ValueError(f"Upstream checkout missing {src}")
    # Use git only to inspect, never to fetch/checkout/update.
    commit = _run(["git", "-C", str(checkout), "rev-parse", "HEAD"], timeout=10)
    if commit != expected_commit:
        raise EnvironmentError("Upstream checkout has drifted from the approved commit")
    dirty = _run(["git", "-C", str(checkout), "status", "--porcelain",
                  "--untracked-files=no"], timeout=10)
    if dirty:
        raise EnvironmentError("Upstream tracked files are modified; verify provenance")

def _python_version(binary: Path) -> str:
    text = _run([str(binary), "-c",
        "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')"],
        timeout=12)
    version = text.split(".")
    if len(version) != 3 or version[0] != "3":
        raise EnvironmentError("Unexpected Python interpreter version")
    if (version[1] not in ("10", "11") or not all(s.isdigit() for s in version)):
        raise EnvironmentError(
            "Model runtimes require Python 3.10 or 3.11; "
            "Text2midi upstream requirements were generated under Python 3.10"
        )
    return text

def plan_environment(model: str, *, checkout, expected_commit, base_python, destination) -> EnvironmentPlan:
    if model not in SUPPORTED:
        raise ValueError("Unknown curated model")
    root = Path(checkout).expanduser().resolve(strict=True)
    if not root.is_dir() or root.is_symlink():
        raise ValueError("Checkout must be an existing directory")
    dest = Path(destination).expanduser().resolve()
    if not dest.parent.is_dir() or dest == root or dest in root.parents or root in dest.parents:
        raise ValueError("New environment must be outside upstream checkout")
    if dest.exists() or dest.is_symlink():
        raise FileExistsError(f"Environment already exists: {dest}")
    binary = Path(base_python).expanduser().resolve(strict=True)
    if not binary.is_file():
        raise ValueError("Base Python interpreter must be an existing file")
    _inspect_checkout(model, root, expected_commit)
    requirements_hash = _digest(_requirements(root))
    return EnvironmentPlan(model, root, expected_commit, requirements_hash,
                           binary, _python_version(binary), dest)

def create_environment(plan: EnvironmentPlan, *, confirm: bool = False) -> dict:
    if not confirm:
        raise PermissionError("Environment creation requires --confirm-create")
    # Re-evaluate upstream commit, dependency snapshot and destination after user consent.
    fresh = plan_environment(
        plan.model, checkout=plan.checkout, expected_commit=plan.expected_commit,
        base_python=plan.interpreter, destination=plan.destination)
    if fresh.requirements_sha256 != plan.requirements_sha256:
        raise EnvironmentError("Requirements changed after planning")
    # venv writes into this user-chosen new directory; no pip network operations.
    plan.destination.mkdir(mode=0o700)
    try:
        _run([str(plan.interpreter), "-m", "venv", str(plan.destination)],
             timeout=240)
        runtime = venv_python(plan.destination)
        if not runtime.is_file():
            raise EnvironmentError("venv Python executable is missing")
        verified = _python_version(runtime)
        if verified != plan.python_version:
            raise EnvironmentError("venv Python does not match base interpreter")
        data = {**plan.as_dict(), "venv_python": str(runtime),
                "state": "created", "installed": False}
        marker = plan.destination / MARKER
        with marker.open("x", encoding="utf-8") as file:
            json.dump(data, file, indent=2, ensure_ascii=False)
        return data
    except BaseException:
        # Do not recursively remove a partially created env; report its location
        # instead of risking deletion of user or concurrent process files.
        raise

def _read_managed_environment(destination) -> dict:
    dest = Path(destination).expanduser().resolve(strict=True)
    marker = dest / MARKER
    if not marker.is_file() or marker.is_symlink():
        raise EnvironmentError("Not a MIDIVOLT-managed environment")
    try:
        data = json.loads(marker.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        raise EnvironmentError("Invalid managed environment manifest") from exc
    if not isinstance(data, dict) or data.get("environment") != str(dest):
        raise EnvironmentError("Environment ownership/path mismatch")
    required = ("model", "checkout", "expected_commit",
                "requirements_sha256", "venv_python")
    if any(not isinstance(data.get(k), str) for k in required):
        raise EnvironmentError("Malformed environment manifest")
    if data["model"] not in SUPPORTED:
        raise EnvironmentError("Unknown environment model")
    if Path(data["venv_python"]) != venv_python(dest):
        raise EnvironmentError("Unexpected environment Python path")
    return data

def install_requirements(destination, *, confirm=False, allow_network=False,
                         wheelhouse=None, timeout=2400) -> dict:
    """Explicit opt-in pip install using exact upstream requirements snapshot."""
    if not confirm:
        raise PermissionError("Installation requires --confirm-install")
    if allow_network == bool(wheelhouse):
        raise ValueError("Choose exactly one: --allow-network OR --wheelhouse")
    if not isinstance(timeout, (int, float)) or not 60 <= timeout <= 7200:
        raise ValueError("Install timeout must be 60..7200 seconds")
    data = _read_managed_environment(destination)
    root = Path(data["checkout"])
    _inspect_checkout(data["model"], root, data["expected_commit"])
    if _digest(_requirements(root)) != data["requirements_sha256"]:
        raise EnvironmentError("Upstream requirements changed; create a fresh environment")
    if data.get("installed"):
        raise EnvironmentError("Environment was already installed; refuse implicit upgrade")
    if wheelhouse:
        wheels = Path(wheelhouse).expanduser().resolve(strict=True)
        if not wheels.is_dir():
            raise ValueError("Wheelhouse must be a directory")
    if wheelhouse:
        # pip --no-index alone does not prohibit direct URLs in requirements.
        # This project deliberately supports only ordinary package specs in
        # offline mode; nested requirement files, editable installs, URLs and
        # index overrides are refused before launching pip.
        for raw in _requirements(root).read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            clean = line.split("#", 1)[0].strip().lower()
            if (line.startswith("-") or "://" in clean or "git+" in clean or
                    " @ " in clean or clean.startswith(("file:", "./", "../", "/"))):
                raise EnvironmentError(
                    "Offline install refuses requirement options, URLs and nested files"
                )
    python = Path(data["venv_python"])
    if not python.is_file():
        raise EnvironmentError("Managed Python missing")
    command = [str(python), "-m", "pip", "install", "--no-input",
               "--disable-pip-version-check"]
    if wheelhouse:
        command += ["--no-index", "--find-links", str(wheels)]
    command += ["--requirement", str(_requirements(root))]
    # model README and checkpoints remain external; install dependencies only.
    env = os.environ.copy()
    env["PIP_NO_INPUT"] = "1"
    if not allow_network:
        env["PIP_NO_INDEX"] = "1"
    _run(command, cwd=str(root), env=env, timeout=timeout)
    data["installed"] = True
    data["state"] = "dependencies_installed"
    data["installed_network_used"] = bool(allow_network)
    data["freeze"] = _run([str(python), "-m", "pip", "freeze"], timeout=60).splitlines()
    # Atomic manifest update; the environment itself has already changed.
    marker = Path(destination) / MARKER
    snapshot = marker.with_name(MARKER + ".tmp")
    snapshot.write_text(json.dumps(data, indent=2, ensure_ascii=False),
                        encoding="utf-8")
    os.replace(snapshot, marker)
    return data

def verify_environment(destination, *, import_model: bool = False) -> dict:
    """Version/source check by default. Model code imports require user opt-in."""
    data = _read_managed_environment(destination)
    root = Path(data["checkout"])
    _inspect_checkout(data["model"], root, data["expected_commit"])
    if _digest(_requirements(root)) != data["requirements_sha256"]:
        raise EnvironmentError("Requirements hash differs from installed plan")
    python = Path(data["venv_python"])
    version = _python_version(python)
    result = {
        "model": data["model"], "python": str(python), "version": version,
        "commit": data["expected_commit"],
        "requirements_sha256": data["requirements_sha256"],
        "installed": bool(data.get("installed")),
        "source_and_requirements_verified": True,
        "model_import_verified": False,
        "real_inference_verified": False,
    }
    if import_model:
        imports = ("from model.transformer_model import Transformer" if data["model"] == "text2midi"
                   else "from anticipation.sample import generate; "
                        "from anticipation.convert import events_to_midi")
        script = (
            "import sys, json, torch, transformers; "
            "sys.path.insert(0, sys.argv[1]); "
            + imports
            + "; print(json.dumps({'torch':torch.__version__, "
              "'transformers':transformers.__version__, "
              "'cuda':torch.cuda.is_available()}))"
        )
        env = os.environ.copy()
        env.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1")
        output = _run([str(python), "-c", script, str(root)],
                      cwd=str(root), env=env, timeout=180)
        values = json.loads(output.splitlines()[-1])
        result["model_import_verified"] = True
        result["packages"] = values
    return result
