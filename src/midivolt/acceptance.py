"""Actual model inference acceptance, separate from mocked unit tests.

This tool invokes the real upstream model and records success ONLY after an
actual child process produces a valid, reviewed MIDI. No weights are bundled.
"""
from __future__ import annotations
from hashlib import sha256
import json
from pathlib import Path
import time

from .environments import (
    _read_managed_environment, verify_environment, venv_python,
)
from .io import read_midi
from .model_adapters import generate_candidate
from .review_engine import _save_new_json, check_proposal


def acceptance_run(*, model: str, environment, checkout, checkpoint,
                   source, out, manifest, report, locked_tracks,
                   confirm_inference=False, **model_options):
    if not confirm_inference:
        raise PermissionError(
            "Real model execution requires --confirm-inference. "
            "Only run trusted local checkpoints and upstream code."
        )
    state = _read_managed_environment(environment)
    if state["model"] != model:
        raise ValueError("Selected model does not match managed environment")
    if not state.get("installed"):
        raise ValueError("Install the model dependencies before acceptance")
    expected_checkout = Path(state["checkout"]).resolve()
    if Path(checkout).expanduser().resolve() != expected_checkout:
        raise ValueError("Managed upstream checkout differs from supplied checkout")
    paths = [Path(x).expanduser().resolve()
             for x in (source, out, manifest, report)]
    if len(set(paths)) != len(paths):
        raise ValueError("Source, candidate, manifest and report must be distinct")
    if paths[3].exists():
        raise FileExistsError("Acceptance report must not already exist")
    if paths[3].suffix.lower() != ".json":
        raise ValueError("Acceptance report must be a JSON file")
    if not locked_tracks:
        raise ValueError("Real acceptance requires at least one locked source track")

    # Validate provenance before launching any model code.
    verified = verify_environment(environment, import_model=False)
    start = time.monotonic()
    result = generate_candidate(
        model=model, python_executable=venv_python(Path(environment).resolve()),
        checkout=expected_checkout, checkpoint=checkpoint,
        source_path=source, output_path=out, manifest_path=manifest,
        locked_tracks=locked_tracks, **model_options)
    elapsed = round(time.monotonic() - start, 3)
    proposal, diff = check_proposal(manifest)
    if diff["locked_tracks"] != list(locked_tracks):
        raise ValueError("Locked tracks changed in acceptance manifest")
    candidate = read_midi(out)
    if diff["notes_added"] == 0:
        raise ValueError("Model generated no new MIDI notes to accept")
    evaluation = {
        "model": model,
        "real_inference_completed": True,
        "execution_mode": "external_upstream_checkpoint",
        "elapsed_seconds": elapsed,
        "python": verified["python"],
        "upstream_source_commit": verified["commit"],
        "requirements_sha256": verified["requirements_sha256"],
        "source_sha256": proposal["source_sha256"],
        "candidate_sha256": proposal["candidate_sha256"],
        "source": str(paths[0]),
        "candidate": str(paths[1]),
        "manifest": str(paths[2]),
        "tracks": result.tracks,
        "note_count": result.notes,
        "new_notes": diff["notes_added"],
        "locked_tracks_verified": list(locked_tracks),
        "tempo_bpm_initial": float(candidate.get_tempo_changes()[1][0]),
        "musical_quality_verified": False,
        "cubase_import_verified": False,
        "gpu_benchmark_verified": False,
        "model_weights_provenance_reviewed": False,
    }
    _save_new_json(paths[3], evaluation)
    return evaluation
