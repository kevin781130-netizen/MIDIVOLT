"""Real, opt-in Text2midi strict-composition acceptance.

No fake inference fallback. A success record is written only after the
existing, separately installed upstream model actually generates notes,
passes role validation, and produces a hash-bound review proposal.
A passed inference test does NOT clear training data or music copyright.
"""
from __future__ import annotations

from hashlib import sha256
from math import isfinite
from pathlib import Path
import re
import time

from .environments import _read_managed_environment, verify_environment, venv_python
from .io import read_midi, write_midi
from .local_model_provider import LocalText2MidiProvider
from .part_orchestrator import compose_strict_parts
from .review_engine import _save_new_json, check_proposal, create_proposal

_HEX_SHA256 = re.compile(r"^[a-f0-9]{64}$")


def _hash_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _trusted_asset(path, expected_sha256: str, label: str) -> tuple[Path, str]:
    if not isinstance(expected_sha256, str) or not _HEX_SHA256.fullmatch(expected_sha256):
        raise ValueError(f"{label}: expected SHA-256 must be 64 lowercase hex characters.")
    file = Path(path).expanduser()
    if file.is_symlink():
        raise ValueError(f"{label}: symlink assets are not accepted.")
    file = file.resolve(strict=True)
    if not file.is_file():
        raise ValueError(f"{label}: must be an existing file.")
    actual = _hash_file(file)
    if actual != expected_sha256:
        raise ValueError(f"{label}: SHA-256 mismatch; refusing to load asset.")
    return file, actual


def validate_acceptance_inputs(
    *, environment, checkout, checkpoint, checkpoint_sha256, vocab,
    vocab_sha256, t5_dir, source, candidate, manifest, report,
    locked_tracks,
) -> dict:
    """Read-only provenance and output-path checks; no inference or imports."""
    state = _read_managed_environment(environment)
    if state["model"] != "text2midi" or not state.get("installed"):
        raise ValueError("A managed, installed Text2midi environment is required.")
    verified = verify_environment(environment, import_model=False)
    if verified["model"] != "text2midi" or not verified["installed"]:
        raise ValueError("Text2midi managed environment validation failed.")
    upstream = Path(checkout).expanduser().resolve(strict=True)
    if upstream != Path(state["checkout"]).resolve():
        raise ValueError("Supplied model checkout does not match pinned managed environment.")
    weights, weights_digest = _trusted_asset(checkpoint, checkpoint_sha256, "checkpoint")
    vocabulary, vocabulary_digest = _trusted_asset(vocab, vocab_sha256, "vocabulary")
    tokenizer = Path(t5_dir).expanduser()
    if tokenizer.is_symlink() or not tokenizer.is_dir():
        raise ValueError("Local T5 tokenizer directory must be an existing, non-symlink directory.")
    tokenizer = tokenizer.resolve(strict=True)
    # Prevent successful-looking provenance from an empty tokenizer directory.
    if not (tokenizer / "tokenizer_config.json").is_file():
        raise ValueError("Local T5 tokenizer is missing tokenizer_config.json.")
    paths = [Path(x).expanduser().resolve() for x in (source, candidate, manifest, report)]
    if len(set(paths)) != 4:
        raise ValueError("Source/candidate/manifest/report must be distinct.")
    src, dst, plan, result_file = paths
    if not src.is_file() or src.suffix.lower() not in (".mid", ".midi"):
        raise ValueError("Source must be an existing MIDI file.")
    for path, suffixes in ((dst, (".mid", ".midi")), (plan, (".json",)), (result_file, (".json",))):
        if path.suffix.lower() not in suffixes or not path.parent.is_dir():
            raise ValueError(f"Output must have {suffixes} extension and existing parent directory.")
        if path.exists() or path.is_symlink():
            raise FileExistsError(f"Acceptance output already exists: {path}")
    if not locked_tracks or len(set(locked_tracks)) != len(locked_tracks):
        raise ValueError("Locked tracks must be supplied exactly once each.")
    original = read_midi(src)
    if any(type(i) is not int or not 0 <= i < len(original.instruments) for i in locked_tracks):
        raise ValueError("Locked track index is invalid.")
    if src in (weights, vocabulary) or weights == vocabulary or tokenizer in paths:
        raise ValueError("Model assets and MIDI paths must be distinct.")
    return {
        "environment": Path(environment).expanduser().resolve(),
        "checkout": upstream, "checkpoint": weights, "vocab": vocabulary,
        "t5_dir": tokenizer, "source": src, "candidate": dst,
        "manifest": plan, "report": result_file, "verified": verified,
        "checkpoint_sha256": weights_digest,
        "vocab_sha256": vocabulary_digest,
        "source_sha256": _hash_file(src),
    }


def run_composition_acceptance(
    *, confirm_inference: bool = False, environment, checkout, checkpoint,
    checkpoint_sha256, vocab, vocab_sha256, t5_dir, source, candidate,
    manifest, report, prompt: str, locked_tracks: list[int],
    program_assignments=None, seed=42, max_new_tracks=16,
    max_total_notes=20000, minimum_structure_score=0.75,
    quality_retries=1, harmonic_key=None, harmonic_chords=None,
    beats_per_chord=4.0, minimum_harmony_score=None,
    timeout=1800.0, temperature=0.9, max_tokens=2000,
) -> dict:
    """Execute the real installed model only after explicit operator consent.

    SHA-bound output remains a *candidate*, not an approved or distributable
    music product. The caller cannot pass a fixture-mode generator.
    """
    if not confirm_inference:
        raise PermissionError(
            "Real Text2midi inference requires --confirm-inference; "
            "only execute explicitly trusted upstream code and pickle assets."
        )
    if type(timeout) not in (int, float) or not isfinite(timeout) or not 1 <= timeout <= 7200:
        raise ValueError("Timeout must be finite and in 1..7200 seconds.")
    validated = validate_acceptance_inputs(
        environment=environment, checkout=checkout, checkpoint=checkpoint,
        checkpoint_sha256=checkpoint_sha256, vocab=vocab, vocab_sha256=vocab_sha256,
        t5_dir=t5_dir, source=source, candidate=candidate,
        manifest=manifest, report=report, locked_tracks=locked_tracks,
    )
    model = LocalText2MidiProvider(
        python_executable=venv_python(validated["environment"]),
        checkout=validated["checkout"],
        checkpoint=validated["checkpoint"], vocab_path=validated["vocab"],
        t5_dir=validated["t5_dir"], timeout=timeout,
        temperature=temperature, max_tokens=max_tokens,
    )
    started = time.monotonic()
    composed, plan, diff = compose_strict_parts(
        read_midi(validated["source"]), prompt, model,
        locked_tracks=tuple(locked_tracks),
        program_assignments=program_assignments,
        seed=seed, max_new_tracks=max_new_tracks,
        max_total_notes=max_total_notes,
        minimum_structure_score=minimum_structure_score,
        quality_retries=quality_retries,
        harmonic_key=harmonic_key, harmonic_chords=harmonic_chords,
        beats_per_chord=beats_per_chord,
        minimum_harmony_score=minimum_harmony_score,
    )
    elapsed = round(time.monotonic() - started, 3)
    # Abort if source or model assets changed during (potentially long) inference.
    if (_hash_file(validated["source"]) != validated["source_sha256"] or
            _hash_file(validated["checkpoint"]) != validated["checkpoint_sha256"] or
            _hash_file(validated["vocab"]) != validated["vocab_sha256"]):
        raise ValueError("Source or model assets changed during inference.")
    write_midi(composed, validated["candidate"])
    create_proposal(
        validated["source"], validated["candidate"], validated["manifest"],
        locked_tracks=locked_tracks,
    )
    proposal, rereview = check_proposal(validated["manifest"])
    if diff != rereview or diff["notes_added"] <= 0 or diff["notes_removed"]:
        raise ValueError("Written MIDI candidate differs from validated in-memory result.")
    result = {
        "schema_version": 1, "model": "text2midi",
        "real_inference_completed": True,
        "inference_mode": "trusted_external_checkpoint_only",
        "elapsed_seconds": elapsed,
        "model_python": str(venv_python(validated["environment"])),
        "upstream_commit": validated["verified"]["commit"],
        "requirements_sha256": validated["verified"]["requirements_sha256"],
        "checkpoint_sha256": validated["checkpoint_sha256"],
        "vocab_sha256": validated["vocab_sha256"],
        "source_sha256": proposal["source_sha256"],
        "candidate_sha256": proposal["candidate_sha256"],
        "source": str(validated["source"]),
        "candidate": str(validated["candidate"]),
        "manifest": str(validated["manifest"]),
        "tracks": len(composed.instruments),
        "new_notes": rereview["notes_added"],
        "locked_tracks": list(locked_tracks),
        "quality_policy": plan["quality_policy"],
        "quality_attempts": plan["quality_attempts"],
        "review": rereview,
        "approved_for_use": False,
        "human_music_review_passed": False,
        "cubase_import_verified": False,
        "commercial_training_data_rights_verified": False,
        "commercial_release_ready": False,
    }
    _save_new_json(validated["report"], result)
    return result
