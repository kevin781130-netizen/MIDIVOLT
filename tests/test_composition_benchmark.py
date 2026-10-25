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



# K14 tests re-use the same synthetic K8 engine fixture; all records remain
# synthetic, and a passing replay NEVER proves actual model execution.
from midivolt.composition_verification import verify_benchmark_evidence
from midivolt.composition_verification_cli import main as verify_cli_main


def test_k14_replays_real_midi_and_case_metrics_without_model_execution(tmp_path, monkeypatch):
    args, provider = setup(tmp_path, monkeypatch)
    benchmark.run_composition_benchmark(**args)
    before_calls = len(provider.calls)
    output = tmp_path / "verification01"
    report = verify_benchmark_evidence(args["output_dir"] / "benchmark.json",
                                       output_dir=output)
    assert report["cases_checked"] == 2
    assert report["cases_accepted"] == 2
    assert report["cases_rejected"] == 0
    assert report["file_and_metric_replay_consistent"] is True
    assert report["all_cases_accepted"] is True
    assert report["external_model_execution_independently_verified"] is False
    assert report["cubase_application_verified"] is False
    assert report["commercial_release_ready"] is False
    assert len(list(output.glob("*.audit.json"))) == 2
    assert json.loads((output / "verification.json").read_text()) == report
    assert len(provider.calls) == before_calls


def test_k14_replays_partial_failure_but_never_calls_it_full_pass(tmp_path, monkeypatch):
    args, provider = setup(tmp_path, monkeypatch)
    provider.fail_violin = True
    result = benchmark.run_composition_benchmark(**args)
    assert result["cases_failed"] == 1
    summary = verify_benchmark_evidence(
        args["output_dir"] / "benchmark.json", output_dir=tmp_path / "verified"
    )
    assert summary["file_and_metric_replay_consistent"] is True
    assert summary["cases_accepted"] == 1
    assert summary["cases_rejected"] == 1
    assert summary["all_cases_accepted"] is False
    assert summary["full_suite_completed"] is True
    assert not summary["commercial_release_ready"]


@pytest.mark.parametrize("field,value", [
    ("cases_passed", 99),
    ("model_calls_observed", 100),
    ("whole_case_success_rate", 0.0),
    ("model_call_duration_p95_seconds", 999.0),
    ("complete_case_role_pass_rate", 0.0),
    ("model_execution_independently_attested", True),
    ("commercial_release_ready", True),
])
def test_k14_rejects_manipulated_aggregate_before_final_report(tmp_path, monkeypatch, field, value):
    args, _ = setup(tmp_path, monkeypatch)
    benchmark.run_composition_benchmark(**args)
    manifest = args["output_dir"] / "benchmark.json"
    data = json.loads(manifest.read_text())
    data[field] = value
    manifest.write_text(json.dumps(data))
    out = tmp_path / "verified"
    with pytest.raises(ValueError):
        verify_benchmark_evidence(manifest, output_dir=out)
    assert not (out / "verification.json").exists()


def test_k14_rejects_forged_midi_hash_even_if_benchmark_summary_says_pass(tmp_path, monkeypatch):
    args, _ = setup(tmp_path, monkeypatch)
    benchmark.run_composition_benchmark(**args)
    report = args["output_dir"] / "benchmark.json"
    data = json.loads(report.read_text())
    data["cases"][0]["candidate_sha256"] = "0" * 64
    report.write_text(json.dumps(data))
    out = tmp_path / "verified"
    with pytest.raises(ValueError, match="MIDI hashes"):
        verify_benchmark_evidence(report, output_dir=out)
    assert not (out / "verification.json").exists()


def test_k14_rejects_tampered_underlying_candidate(tmp_path, monkeypatch):
    import mido
    args, _ = setup(tmp_path, monkeypatch)
    benchmark.run_composition_benchmark(**args)
    candidate = args["output_dir"] / "piano_a.mid"
    midi = mido.MidiFile(candidate)
    for track in midi.tracks:
        first = next((n for n in track if n.type == "note_on" and n.velocity > 0), None)
        if first:
            first.note = min(first.note + 1, 127)
            break
    midi.save(candidate)
    with pytest.raises(ValueError, match="changed since proposal"):
        verify_benchmark_evidence(
            args["output_dir"] / "benchmark.json", output_dir=tmp_path / "verified"
        )
    assert not (tmp_path / "verified" / "verification.json").exists()


def test_k14_k12_doctor_provenance_mismatch_fails_closed(tmp_path, monkeypatch):
    args, _ = setup(tmp_path, monkeypatch)
    benchmark.run_composition_benchmark(**args)
    doctor = tmp_path / "doctor.json"
    doctor.write_text(json.dumps({
        "kind": "midivolt_k12_text2midi_preinference_doctor",
        "ready_for_inference_attempt": True,
        "commercial_release_ready": False,
        "runtime": {"third_party_packages_imported": True},
        "checkpoint_sha256": "0" * 64,
        "vocab_sha256": args["vocab_sha256"],
        "upstream_commit": "a" * 40,
        "requirements_sha256": "b" * 64,
    }))
    with pytest.raises(ValueError, match="K12/K8 model provenance mismatch"):
        verify_benchmark_evidence(
            args["output_dir"] / "benchmark.json",
            doctor_report=doctor, output_dir=tmp_path / "verified"
        )
    assert not (tmp_path / "verified" / "verification.json").exists()


def test_k14_cli_exits_three_for_verified_but_failed_suite(tmp_path, monkeypatch, capsys):
    args, provider = setup(tmp_path, monkeypatch)
    provider.fail_violin = True
    benchmark.run_composition_benchmark(**args)
    code = verify_cli_main([
        "--benchmark", str(args["output_dir"] / "benchmark.json"),
        "--out-dir", str(tmp_path / "verified"),
    ])
    assert code == 3
    assert '"all_cases_accepted": false' in capsys.readouterr().out


def test_k14_prevents_reuse_of_existing_result_directory(tmp_path, monkeypatch):
    args, _ = setup(tmp_path, monkeypatch)
    benchmark.run_composition_benchmark(**args)
    report = args["output_dir"] / "benchmark.json"
    out = tmp_path / "verified"
    verify_benchmark_evidence(report, output_dir=out)
    original = (out / "verification.json").read_bytes()
    with pytest.raises(FileExistsError, match="NEW"):
        verify_benchmark_evidence(report, output_dir=out)
    assert (out / "verification.json").read_bytes() == original
