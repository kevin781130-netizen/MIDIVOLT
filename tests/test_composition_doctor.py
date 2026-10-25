"""K12 runtime doctor is fixture-tested; no GPU/model inference in CI."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from midivolt import composition_doctor as doctor
from midivolt.composition_doctor_cli import main as cli_main


def ready_inputs(tmp_path, monkeypatch):
    env = tmp_path / "model-env"
    env.mkdir()
    binary = doctor.venv_python(env)
    binary.parent.mkdir(parents=True, exist_ok=True)
    binary.write_bytes(b"fake python placeholder; never executed")
    root = tmp_path / "upstream"
    (root / "model").mkdir(parents=True)
    (root / "model" / "transformer_model.py").write_text(
        "class Transformer:\n"
        "    def __init__(self, device=None):\n"
        "        T5EncoderModel.from_pretrained('google/flan-t5-base')\n"
        "    def generate(self, src): return src\n"
    )
    checkpoint = tmp_path / "checkpoint.bin"
    checkpoint.write_bytes(b"fixture-not-real-weights")
    vocab = tmp_path / "remi.pkl"
    vocab.write_bytes(b"fixture-not-real-pickle")
    t5_dir = tmp_path / "t5"
    t5_dir.mkdir()
    (t5_dir / "tokenizer_config.json").write_text("{}")
    (t5_dir / "config.json").write_text('{"model_type":"t5"}')
    (t5_dir / "model.safetensors").write_bytes(b"not a real model")
    monkeypatch.setattr(
        doctor, "_read_managed_environment",
        lambda _: {"model": "text2midi", "installed": True, "checkout": str(root)},
    )
    monkeypatch.setattr(
        doctor, "verify_environment",
        lambda _, import_model=False: {
            "model": "text2midi", "installed": True,
            "commit": "a" * 40, "requirements_sha256": "b" * 64,
        },
    )
    args = dict(
        environment=env, checkout=root, checkpoint=checkpoint,
        checkpoint_sha256=sha256(checkpoint.read_bytes()).hexdigest(),
        vocab=vocab, vocab_sha256=sha256(vocab.read_bytes()).hexdigest(),
        t5_dir=t5_dir, output_path=tmp_path / "doctor.json",
    )
    return args


def stub_probe(*, imported=False, cuda=False, missing=None):
    return {
        "python_supported": True, "missing_packages": missing or [],
        "third_party_packages_imported": imported,
        "cuda_compute_tested": cuda, "cuda_compute_passed": cuda,
        "cuda_available": cuda, "model_weights_loaded": False,
        "upstream_model_imported": False, "real_inference_verified": False,
    }


def test_metadata_only_report_never_overclaims(tmp_path, monkeypatch):
    args = ready_inputs(tmp_path, monkeypatch)
    called = []
    def fake_run(argv, **kwargs):
        called.append((argv, kwargs))
        return SimpleNamespace(returncode=0, stdout=json.dumps(stub_probe()) + "\n")
    monkeypatch.setattr(doctor.subprocess, "run", fake_run)
    report = doctor.diagnose_composition_runtime(**args)
    assert len(called) == 1
    assert called[0][0][1] == "-I"
    assert called[0][1]["shell"] is False
    assert called[0][1]["env"]["HF_HUB_OFFLINE"] == "1"
    assert "--confirm-imports" not in called[0][0]
    assert report["local_t5"]["encoder_weights_present"]
    assert report["ready_for_inference_attempt"] is False
    assert not report["actual_inference_verified"]
    assert not report["remi_unpickled"]
    assert not report["commercial_release_ready"]
    assert json.loads(args["output_path"].read_text()) == report


def test_explicit_runtime_imports_cannot_claim_inference_or_model_load(tmp_path, monkeypatch):
    args = ready_inputs(tmp_path, monkeypatch)
    commands = []
    def fake_run(argv, **kwargs):
        commands.append(argv)
        return SimpleNamespace(returncode=0, stdout=json.dumps(stub_probe(imported=True)) + "\n")
    monkeypatch.setattr(doctor.subprocess, "run", fake_run)
    data = doctor.diagnose_composition_runtime(**args, confirm_imports=True)
    assert data["ready_for_inference_attempt"] is True
    assert "--confirm-imports" in commands[0]
    assert "--cuda-smoke" not in commands[0]
    assert data["actual_inference_verified"] is False


def test_cuda_requires_actual_smoke_and_is_never_inferred_from_availability(tmp_path, monkeypatch):
    args = ready_inputs(tmp_path, monkeypatch)
    monkeypatch.setattr(doctor.subprocess, "run", lambda *a, **k: SimpleNamespace(
        returncode=0, stdout=json.dumps(stub_probe(imported=True, cuda=False)) + "\n"
    ))
    result = doctor.diagnose_composition_runtime(
        **args, confirm_imports=True, cuda_smoke=True, require_cuda=True
    )
    assert not result["ready_for_inference_attempt"]
    assert any("CUDA" in s for s in result["compatibility_blockers"])


def test_missing_package_is_reported_as_blocker(tmp_path, monkeypatch):
    args = ready_inputs(tmp_path, monkeypatch)
    monkeypatch.setattr(doctor.subprocess, "run", lambda *a, **k: SimpleNamespace(
        returncode=0, stdout=json.dumps(stub_probe(missing=["sentencepiece"])) + "\n"
    ))
    result = doctor.diagnose_composition_runtime(**args)
    assert not result["ready_for_inference_attempt"]
    assert "sentencepiece" in " ".join(result["compatibility_blockers"])


def test_asset_digest_mismatch_prevents_subprocess_or_output(tmp_path, monkeypatch):
    args = ready_inputs(tmp_path, monkeypatch)
    args["checkpoint_sha256"] = "0" * 64
    monkeypatch.setattr(doctor.subprocess, "run", lambda *a, **k: pytest.fail("launched subprocess"))
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        doctor.diagnose_composition_runtime(**args)
    assert not args["output_path"].exists()


def test_cuda_flags_require_opt_in_before_assets(tmp_path):
    with pytest.raises(ValueError, match="confirm-imports"):
        doctor.diagnose_composition_runtime(
            environment=tmp_path, checkout=tmp_path,
            checkpoint=tmp_path, checkpoint_sha256="0"*64,
            vocab=tmp_path, vocab_sha256="0"*64,
            t5_dir=tmp_path, output_path=tmp_path / "out.json",
            cuda_smoke=True,
        )


def test_subprocess_failure_never_creates_report(tmp_path, monkeypatch):
    args = ready_inputs(tmp_path, monkeypatch)
    monkeypatch.setattr(doctor.subprocess, "run", lambda *a, **k: SimpleNamespace(
        returncode=2, stdout="", stderr="upstream secrets in stderr",
    ))
    with pytest.raises(RuntimeError, match="probe failed"):
        doctor.diagnose_composition_runtime(**args, confirm_imports=True)
    assert not args["output_path"].exists()


def test_runtime_probe_metadata_mode_does_not_import_torch(monkeypatch):
    from midivolt.model_runners import runtime_probe
    monkeypatch.setattr(runtime_probe.importlib.metadata, "version", lambda _: "fixture")
    result = runtime_probe.probe()
    assert result["third_party_packages_imported"] is False
    assert result["cuda_compute_passed"] is False
    assert result["real_inference_verified"] is False


def test_cli_codes_do_not_forge_beta_or_inference(monkeypatch, capsys):
    def dummy(**kwargs):
        return {"ready_for_inference_attempt": False, "commercial_release_ready": False}
    monkeypatch.setattr("midivolt.composition_doctor_cli.diagnose_composition_runtime", dummy)
    args = []
    for name in ("env", "checkout", "checkpoint", "checkpoint-sha256",
                 "vocab", "vocab-sha256", "t5-dir", "out"):
        args.extend(("--" + name, "fixture"))
    assert cli_main(args) == 3
    assert '"commercial_release_ready": false' in capsys.readouterr().out



# K15: these fixtures do not load pretrained weights. The fake child process
# simulates only the runner's JSON contract for safety/dispatch testing.
def fake_loaded_model_result():
    return {
        "schema_version": 1,
        "model": "text2midi",
        "mode": "trusted_local_load_only",
        "model_state_dict_strict_loaded": True,
        "local_t5_encoder_initialized": True,
        "local_t5_tokenizer_initialized": True,
        "remi_pickle_deserialized": True,
        "upstream_model_code_imported": True,
        "pretrained_inference_executed": False,
        "midi_written": False,
        "device_type": "cpu",
        "torch_version": "2.5.1",
        "vocab_size": 9000,
        "model_parameter_count": 123456,
        "load_wall_seconds": 0.2,
        "pretrained_model_provenance_independently_attested": False,
        "commercial_release_ready": False,
    }


def test_k15_requires_separate_consent_to_deserialize_trusted_assets(tmp_path, monkeypatch):
    args = ready_inputs(tmp_path, monkeypatch)
    executed = []
    monkeypatch.setattr(doctor.subprocess, "run",
                        lambda *a, **kw: executed.append(kw))
    with pytest.raises(PermissionError, match="--confirm-model-load"):
        doctor.diagnose_composition_runtime(
            **args, confirm_model_load=True, confirm_imports=False
        )
    assert executed == []
    assert not args["output_path"].exists()


def test_k15_successful_stubbed_checkpoint_load_records_no_generation(tmp_path, monkeypatch):
    args = ready_inputs(tmp_path, monkeypatch)
    cmds = []
    def run(command, **kwargs):
        cmds.append((command, kwargs))
        if len(cmds) == 1:
            return SimpleNamespace(returncode=0, stdout=json.dumps(
                stub_probe(imported=True)
            ) + "\n")
        assert len(cmds) == 2
        return SimpleNamespace(returncode=0, stdout=json.dumps(
            fake_loaded_model_result()
        ) + "\n")
    monkeypatch.setattr(doctor.subprocess, "run", run)
    result = doctor.diagnose_composition_runtime(
        **args, confirm_imports=True, confirm_model_load=True
    )
    assert result["ready_for_inference_attempt"] is True
    assert result["trusted_checkpoint_load_requested"] is True
    assert result["operator_checkpoint_load_completed"] is True
    assert result["checkpoint_deserialized"] is True
    assert result["remi_unpickled"] is True
    assert result["upstream_model_imported"] is True
    assert result["checkpoint_load_independently_attested"] is False
    assert result["actual_inference_verified"] is False
    assert result["commercial_release_ready"] is False
    second_argv, second_kwargs = cmds[1]
    assert second_argv[1] == "-I"
    assert "--load-only" in second_argv
    assert "--checkpoint" in second_argv and "--vocab" in second_argv
    assert "--prompt" not in second_argv and "--out" not in second_argv
    assert second_kwargs["shell"] is False
    assert second_kwargs["env"]["TRANSFORMERS_OFFLINE"] == "1"
    assert json.loads(args["output_path"].read_text()) == result


def test_k15_model_load_failure_never_publishes_success(tmp_path, monkeypatch):
    args = ready_inputs(tmp_path, monkeypatch)
    n = []
    def run(argv, **kw):
        n.append(argv)
        if len(n) == 1:
            return SimpleNamespace(returncode=0, stdout=json.dumps(
                stub_probe(imported=True)
            ))
        return SimpleNamespace(
            returncode=1, stdout="", stderr="secret model path plus debug")
    monkeypatch.setattr(doctor.subprocess, "run", run)
    with pytest.raises(RuntimeError, match="could not be strictly loaded") as failure:
        doctor.diagnose_composition_runtime(
            **args, confirm_imports=True, confirm_model_load=True
        )
    assert "secret" not in str(failure.value)
    assert not args["output_path"].exists()


@pytest.mark.parametrize("changed_field,changed", [
    ("model_state_dict_strict_loaded", False),
    ("pretrained_inference_executed", True),
    ("midi_written", True),
    ("model_parameter_count", 0),
    ("commercial_release_ready", True),
])
def test_k15_disallows_false_success_or_forged_inference_claim(
        tmp_path, monkeypatch, changed_field, changed):
    args = ready_inputs(tmp_path, monkeypatch)
    n = []
    def run(argv, **kw):
        n.append(argv)
        if len(n) == 1:
            return SimpleNamespace(
                returncode=0, stdout=json.dumps(stub_probe(imported=True)))
        record = fake_loaded_model_result()
        record[changed_field] = changed
        return SimpleNamespace(returncode=0, stdout=json.dumps(record))
    monkeypatch.setattr(doctor.subprocess, "run", run)
    with pytest.raises(ValueError):
        doctor.diagnose_composition_runtime(
            **args, confirm_imports=True, confirm_model_load=True
        )
    assert not args["output_path"].exists()


def test_k15_mismatched_checkpoint_after_runner_refuses_success(tmp_path, monkeypatch):
    args = ready_inputs(tmp_path, monkeypatch)
    n = []
    def run(argv, **kw):
        n.append(argv)
        if len(n) == 1:
            return SimpleNamespace(returncode=0, stdout=json.dumps(
                stub_probe(imported=True)))
        args["checkpoint"].write_bytes(b"tampered-while-loading")
        return SimpleNamespace(
            returncode=0, stdout=json.dumps(fake_loaded_model_result())
        )
    monkeypatch.setattr(doctor.subprocess, "run", run)
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        doctor.diagnose_composition_runtime(
            **args, confirm_imports=True, confirm_model_load=True
        )
    assert not args["output_path"].exists()


def test_k15_no_load_when_missing_dependencies(tmp_path, monkeypatch):
    args = ready_inputs(tmp_path, monkeypatch)
    cmds = []
    def run(argv, **kw):
        cmds.append(argv)
        return SimpleNamespace(returncode=0, stdout=json.dumps(
            stub_probe(imported=False, missing=["torch"])
        ))
    monkeypatch.setattr(doctor.subprocess, "run", run)
    with pytest.raises(RuntimeError, match="runtime preflight did not pass"):
        doctor.diagnose_composition_runtime(
            **args, confirm_imports=True, confirm_model_load=True
        )
    assert len(cmds) == 1
    assert not args["output_path"].exists()


def test_k15_runner_help_is_safe_without_torch_or_checkpoint(tmp_path, monkeypatch):
    from midivolt.model_runners import text2midi_runner
    import sys
    monkeypatch.setattr(sys, "argv", [
        "text2midi_runner.py", "--help"
    ])
    with pytest.raises(SystemExit) as exited:
        text2midi_runner.main()
    assert exited.value.code == 0
