"""K13 real K8 orchestration under synthetic providers (NO pretrained weights)."""
from __future__ import annotations

from hashlib import sha256
import json

import pretty_midi
import pytest

from midivolt import composition_acceptance as acceptance
from midivolt import composition_benchmark as benchmark
from midivolt.composition_benchmark_cli import main as cli_main
from midivolt.io import write_midi


def setup(tmp_path, monkeypatch):
    checkout = tmp_path / "Text2midi"
    (checkout / "model").mkdir(parents=True)
    (checkout / "model" / "transformer_model.py").write_text(
        "class Transformer:\n"
        "    def __init__(self, device=None):\n"
        "        T5EncoderModel.from_pretrained('google/flan-t5-base')\n"
        "    def generate(self): pass\n"
    )
    env = tmp_path / "managed-env"
    env.mkdir()
    checkpoint = tmp_path / "weights.bin"
    checkpoint.write_bytes(b"fake-checkpoint-never-loaded")
    vocabulary = tmp_path / "vocab.pkl"
    vocabulary.write_bytes(b"fake-vocab-never-unpickled")
    t5 = tmp_path / "t5"
    t5.mkdir()
    (t5 / "tokenizer_config.json").write_text("{}")
    (t5 / "config.json").write_text('{"model_type":"t5"}')
    (t5 / "model.safetensors").write_bytes(b"fake-t5-weights-never-loaded")

    src = pretty_midi.PrettyMIDI(initial_tempo=100)
    lead = pretty_midi.Instrument(program=73, name="Source melody")
    lead.notes.append(pretty_midi.Note(95, 72, 0.0, 0.8))
    src.instruments.append(lead)
    source = tmp_path / "source.mid"
    write_midi(src, source)

    suite_path = tmp_path / "suite.json"
    suite_path.write_text(json.dumps({
        "schema_version": 1,
        "cases": [
            {"id": "piano_a", "prompt": "piano", "seed": 41},
            {"id": "two_roles", "prompt": "piano and violin", "seed": 51},
        ],
    }), encoding="utf-8")
    monkeypatch.setattr(
        acceptance, "_read_managed_environment",
        lambda _: {"model": "text2midi", "installed": True, "checkout": str(checkout)},
    )
    monkeypatch.setattr(
        acceptance, "verify_environment",
        lambda _, import_model=False: {
            "model": "text2midi", "installed": True,
            "commit": "a" * 40, "requirements_sha256": "b" * 64,
        },
    )

    class FixtureProvider:
        name = "fixture_no_pretrained_model"
        calls = []
        fail_violin = False

        def __init__(self, **kwargs):
            pass

        def generate(self, prompt, *, tempo, seed=None):
            self.calls.append((seed, tempo))
            if self.fail_violin and "Violin" in prompt:
                raise RuntimeError("fixture crashed intentionally: no model was run")
            result = pretty_midi.PrettyMIDI(initial_tempo=tempo)
            program = 40 if "Violin" in prompt else 0
            track = pretty_midi.Instrument(program=program, name="fixture")
            track.notes.append(pretty_midi.Note(100, 67 if program == 40 else 60, 0, 0.5))
            result.instruments.append(track)
            return result

    FixtureProvider.calls = []
    FixtureProvider.fail_violin = False
    monkeypatch.setattr(acceptance, "LocalText2MidiProvider", FixtureProvider)

    common = dict(
        confirm_inference=True, suite=suite_path,
        output_dir=tmp_path / "run01", source=source,
        locked_tracks=(0,), environment=env, checkout=checkout,
        checkpoint=checkpoint,
        checkpoint_sha256=sha256(checkpoint.read_bytes()).hexdigest(),
        vocab=vocabulary,
        vocab_sha256=sha256(vocabulary.read_bytes()).hexdigest(),
        t5_dir=t5, quality_retries=0,
    )
    return common, FixtureProvider


def test_two_synthetic_cases_using_real_k8_validation(tmp_path, monkeypatch):
    args, provider = setup(tmp_path, monkeypatch)
    original = args["source"].read_bytes()
    result = benchmark.run_composition_benchmark(**args)
    assert result["cases_executed"] == 2
    assert result["cases_passed"] == 2
    assert result["whole_case_success_rate"] == 1.0
    assert result["complete_case_role_pass_rate"] == 1.0
    assert result["model_calls_observed"] == 3
    assert result["model_call_return_rate"] == 1.0
    assert len(provider.calls) == 3
    assert result["successful_case_structure_score_mean"] == 1.0
    assert result["commercial_release_ready"] is False
    assert result["model_execution_independently_attested"] is False
    assert result["musical_accuracy_ground_truth_verified"] is False
    assert [p["role"] for p in result["cases"][1]["role_attempts"]] == ["piano", "violin"]
    for record in result["cases"]:
        assert record["success"]
        assert record["model_calls"]
        assert all(event["elapsed_seconds"] >= 0 for event in record["model_calls"])
        assert (args["output_dir"] / (record["id"] + ".acceptance.json")).is_file()
        assert (args["output_dir"] / (record["id"] + ".proposal.json")).is_file()
    assert args["source"].read_bytes() == original
    assert json.loads((args["output_dir"] / "benchmark.json").read_text()) == result
    assert "fixture crashed" not in json.dumps(result)


def test_partial_failure_counts_in_denominator_with_no_success_manifest(tmp_path, monkeypatch):
    args, provider = setup(tmp_path, monkeypatch)
    provider.fail_violin = True
    result = benchmark.run_composition_benchmark(**args)
    assert result["cases_passed"] == 1
    assert result["cases_failed"] == 1
    assert result["whole_case_success_rate"] == 0.5
    assert result["complete_case_role_pass_rate"] == 0.3333
    assert result["model_calls_observed"] == 3
    assert result["model_calls_returned"] == 2
    assert result["model_call_return_rate"] == 0.6667
    failed = result["cases"][1]
    assert failed["error_type"] == "RuntimeError"
    assert failed["failure_stage"] == "external_model_or_adapter"
    assert failed["partial_output_may_exist"]
    assert failed["model_calls"][-1]["status"] == "error"
    assert failed["model_calls"][-1]["error_type"] == "RuntimeError"
    assert not (args["output_dir"] / "two_roles.acceptance.json").exists()
    assert "fixture crashed intentionally" not in json.dumps(result)


def test_consent_required_before_read_or_output(tmp_path):
    with pytest.raises(PermissionError, match="confirm-inference"):
        benchmark.run_composition_benchmark(
            confirm_inference=False, suite=tmp_path / "absent.json",
            output_dir=tmp_path / "run", source=tmp_path / "absent.mid",
            locked_tracks=(0,), environment=tmp_path, checkout=tmp_path,
            checkpoint=tmp_path, checkpoint_sha256="0" * 64,
            vocab=tmp_path, vocab_sha256="0" * 64, t5_dir=tmp_path,
        )
    assert not (tmp_path / "run").exists()


def test_invalid_case_rejected_before_first_model_run(tmp_path, monkeypatch):
    args, provider = setup(tmp_path, monkeypatch)
    args["suite"].write_text(json.dumps({
        "schema_version": 1,
        "cases": [
            {"id": "good", "prompt": "piano", "seed": 41},
            {"id": "../bad", "prompt": "violin", "seed": 42},
        ],
    }))
    with pytest.raises(ValueError, match="filesystem-safe"):
        benchmark.run_composition_benchmark(**args)
    assert not args["output_dir"].exists()
    assert not provider.calls


def test_reused_output_dir_rejected_and_original_report_unchanged(tmp_path, monkeypatch):
    args, provider = setup(tmp_path, monkeypatch)
    benchmark.run_composition_benchmark(**args)
    previous = (args["output_dir"] / "benchmark.json").read_bytes()
    calls = len(provider.calls)
    with pytest.raises(FileExistsError):
        benchmark.run_composition_benchmark(**args)
    assert len(provider.calls) == calls
    assert (args["output_dir"] / "benchmark.json").read_bytes() == previous


def test_fail_fast_reports_subset_without_claiming_full_suite(tmp_path, monkeypatch):
    args, provider = setup(tmp_path, monkeypatch)
    provider.fail_violin = True
    args["suite"].write_text(json.dumps({
        "schema_version": 1, "cases": [
            {"id": "first", "prompt": "violin", "seed": 51},
            {"id": "second", "prompt": "piano", "seed": 60},
        ]
    }))
    result = benchmark.run_composition_benchmark(**args, fail_fast=True)
    assert result["suite_cases_declared"] == 2
    assert result["cases_executed"] == 1
    assert result["execution_stopped_early"]
    assert result["cases_failed"] == 1
    assert not (args["output_dir"] / "second.acceptance.json").exists()


def test_validation_rejects_incomplete_program_selection(tmp_path, monkeypatch):
    args, provider = setup(tmp_path, monkeypatch)
    args["suite"].write_text(json.dumps({
        "schema_version": 1, "cases": [
            {"id": "bass", "prompt": "bass", "seed": 1},
        ]
    }))
    with pytest.raises(ValueError, match="requires explicit"):
        benchmark.run_composition_benchmark(**args)
    assert not args["output_dir"].exists()


def test_cli_refuses_implicit_model_execution(capsys):
    args = []
    for arg in ("suite", "out-dir", "source", "env", "checkout",
                "checkpoint", "checkpoint-sha256", "vocab", "vocab-sha256", "t5-dir"):
        args += ["--" + arg, "placeholder"]
    args += ["--lock", "0"]
    assert cli_main(args) == 2
    assert "PermissionError" in capsys.readouterr().err


def test_suite_max_cases_bounded(tmp_path, monkeypatch):
    args, provider = setup(tmp_path, monkeypatch)
    args["suite"].write_text(json.dumps({
        "schema_version": 1, "cases": [
            {"id": f"case_{i}", "prompt": "piano", "seed": i}
            for i in range(9)
        ]
    }))
    with pytest.raises(ValueError, match="1..8"):
        benchmark.run_composition_benchmark(**args)
    assert not args["output_dir"].exists()


def test_failed_preflight_yields_report_without_claiming_model_calls(tmp_path, monkeypatch):
    args, provider = setup(tmp_path, monkeypatch)
    args["checkpoint_sha256"] = "0" * 64
    result = benchmark.run_composition_benchmark(**args, fail_fast=True)
    assert result["model_calls_observed"] == 0
    assert result["cases_failed"] == 1
    assert not (args["output_dir"] / "piano_a.acceptance.json").exists()
    assert not provider.calls
