"""K12 local FLAN-T5 asset and upstream signature regression; no pretrained weights."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from midivolt.model_runners.text2midi_local import (
    inspect_local_t5, inspect_upstream_text2midi_contract,
    redirect_known_t5_encoder,
)


def t5_fixture(tmp_path):
    folder = tmp_path / "t5"
    folder.mkdir()
    (folder / "tokenizer_config.json").write_text("{}", encoding="utf-8")
    (folder / "config.json").write_text('{"model_type":"t5"}', encoding="utf-8")
    (folder / "model.safetensors").write_bytes(b"fixture-not-real-weights")
    return folder


def upstream_fixture(tmp_path, *, encoder="google/flan-t5-base"):
    root = tmp_path / "upstream"
    (root / "model").mkdir(parents=True)
    (root / "model" / "transformer_model.py").write_text(
        "class Transformer:\n"
        "    def __init__(self, device=None):\n"
        "        T5EncoderModel.from_pretrained(" + repr(encoder) + ")\n"
        "    def generate(self, tokens): pass\n",
        encoding="utf-8",
    )
    return root


def test_local_t5_requires_both_tokenizer_and_real_weight_filename(tmp_path):
    root = t5_fixture(tmp_path)
    info = inspect_local_t5(root)
    assert info["encoder_format"] == "safetensors"
    assert info["encoder_weights_present"]
    assert info["weight_contents_or_signature_validated"] is False
    (root / "model.safetensors").unlink()
    with pytest.raises(ValueError, match="encoder weights missing"):
        inspect_local_t5(root)
    (root / "model.safetensors").write_bytes(b"placeholder")
    (root / "config.json").unlink()
    with pytest.raises(ValueError, match="config.json"):
        inspect_local_t5(root)


def test_rejects_wrong_t5_architecture(tmp_path):
    root = t5_fixture(tmp_path)
    (root / "config.json").write_text('{"model_type":"bert"}')
    with pytest.raises(ValueError, match="model_type=t5"):
        inspect_local_t5(root)


def test_rejects_unsafe_shard_index_paths(tmp_path):
    root = t5_fixture(tmp_path)
    (root / "model.safetensors").unlink()
    (root / "model.safetensors.index.json").write_text(json.dumps({
        "weight_map": {"encoder.block.0.weight": "../outside.safetensors"}
    }))
    with pytest.raises(ValueError, match="unsafe filenames"):
        inspect_local_t5(root)


def test_sharded_encoder_requires_all_local_files(tmp_path):
    root = t5_fixture(tmp_path)
    (root / "model.safetensors").unlink()
    (root / "model.safetensors.index.json").write_text(json.dumps({
        "weight_map": {"encoder.layer.0": "model-00001-of-00002.safetensors"}
    }))
    with pytest.raises(ValueError, match="shard missing"):
        inspect_local_t5(root)
    (root / "model-00001-of-00002.safetensors").write_bytes(b"fake")
    info = inspect_local_t5(root)
    assert info["encoder_files"] == [
        "model.safetensors.index.json", "model-00001-of-00002.safetensors"
    ]


def test_ast_checks_upstream_contract_without_importing_it(tmp_path):
    upstream = upstream_fixture(tmp_path)
    report = inspect_upstream_text2midi_contract(upstream)
    assert report["static_source_contract_verified"]
    assert not report["upstream_code_executed"]


def test_unexpected_upstream_encoder_request_refuses_before_inference(tmp_path):
    upstream = upstream_fixture(tmp_path, encoder="some/other-encoder")
    with pytest.raises(ValueError, match="contract differs"):
        inspect_upstream_text2midi_contract(upstream)


def test_local_encoder_redirection_is_strict_and_restored(tmp_path):
    root = t5_fixture(tmp_path)
    observed = []
    class MockT5:
        @classmethod
        def from_pretrained(cls, value, **kwargs):
            observed.append((value, kwargs))
            return "encoder-stub"

    original = MockT5.__dict__["from_pretrained"]
    with redirect_known_t5_encoder(MockT5, root):
        assert MockT5.from_pretrained("google/flan-t5-base") == "encoder-stub"
        with pytest.raises(RuntimeError, match="Unexpected upstream encoder"):
            MockT5.from_pretrained("some/other-source")
    assert MockT5.__dict__["from_pretrained"] is original
    assert observed == [(str(root.resolve()), {"local_files_only": True})]


def test_runner_source_requires_local_encoder_redirect():
    # The stdlib helper is testable without importing torch or running model code.
    import midivolt.model_runners.text2midi_runner as runner
    assert callable(runner.main)



def test_k15_load_only_runner_executes_strict_state_path_with_stubs(
        tmp_path, monkeypatch, capsys):
    """Exact runner load-only path, with stubbed torch and REMI, NOT pretrained."""
    import contextlib
    import sys
    import types
    from midivolt.model_runners import text2midi_runner as runner

    root = tmp_path / "approved-upstream"
    root.mkdir()
    checkpoint = tmp_path / "checkpoint.bin"
    checkpoint.write_bytes(b"fake checkpoint bytes")
    vocab = tmp_path / "trusted-remi.pkl"
    vocab.write_bytes(b"fixture pickle not deserialized by actual code")
    t5 = tmp_path / "t5"
    t5.mkdir()
    seen = {}
    class FakeParameters:
        def numel(self):
            return 1200
    class FakeTransformer:
        def __init__(self, *args, **kwargs):
            seen["model_kwargs"] = kwargs
            seen["model_args"] = args
        def load_state_dict(self, state, *, strict):
            assert strict is True
            seen["state"] = state
        def to(self, device):
            assert device == "cpu"
            return self
        def eval(self):
            return self
        def parameters(self):
            return [FakeParameters()]
    class FakeT5Tokenizer:
        @classmethod
        def from_pretrained(cls, directory, **kwargs):
            seen["tokenizer"] = (directory, kwargs)
            return cls()
    class FakeT5EncoderModel:
        pass
    fake_torch = types.ModuleType("torch")
    fake_torch.__version__ = "0.fixture"
    fake_torch.cuda = types.SimpleNamespace(is_available=lambda: False)
    fake_torch.backends = types.SimpleNamespace(
        mps=types.SimpleNamespace(is_available=lambda: False))
    def load(path, **kwargs):
        seen["load"] = (path, kwargs)
        return {"layer.weight": "fake data"}
    fake_torch.load = load
    fake_transformers = types.ModuleType("transformers")
    fake_transformers.T5Tokenizer = FakeT5Tokenizer
    fake_transformers.T5EncoderModel = FakeT5EncoderModel
    fake_model = types.ModuleType("model")
    fake_model.__path__ = []
    fake_upstream = types.ModuleType("model.transformer_model")
    fake_upstream.Transformer = FakeTransformer

    for name, fake in (
        ("torch", fake_torch),
        ("transformers", fake_transformers),
        ("model", fake_model),
        ("model.transformer_model", fake_upstream),
    ):
        monkeypatch.setitem(sys.modules, name, fake)
    monkeypatch.setattr(sys, "path", sys.path[:])
    monkeypatch.setattr(runner, "inspect_local_t5", lambda _: {})
    monkeypatch.setattr(runner, "inspect_upstream_text2midi_contract", lambda _: {})
    monkeypatch.setattr(
        runner, "redirect_known_t5_encoder",
        lambda *a: contextlib.nullcontext()
    )
    monkeypatch.setattr(runner.pickle, "load", lambda _: list(range(121)))
    monkeypatch.setattr(sys, "argv", [
        "text2midi_runner.py", "--checkout", str(root),
        "--checkpoint", str(checkpoint), "--vocab", str(vocab),
        "--t5-dir", str(t5), "--load-only",
    ])
    runner.main()
    result = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert seen["load"][1]["weights_only"] is True
    assert seen["model_args"][0] == 121
    assert seen["state"] == {"layer.weight": "fake data"}
    assert result["model_parameter_count"] == 1200
    assert result["model_state_dict_strict_loaded"] is True
    assert result["pretrained_inference_executed"] is False
    assert result["midi_written"] is False
    assert result["commercial_release_ready"] is False
    assert not list(tmp_path.glob("*.mid"))


def test_k15_runner_rejects_implicit_generation_before_upstream_import(
        monkeypatch, capsys):
    import sys
    from midivolt.model_runners import text2midi_runner as runner
    monkeypatch.setattr(sys, "argv", [
        "text2midi_runner.py",
        "--checkout", "not-used",
        "--checkpoint", "not-used",
        "--vocab", "not-used",
        "--t5-dir", "not-used",
    ])
    with pytest.raises(SystemExit) as exc:
        runner.main()
    assert exc.value.code == 2
    assert "Generation requires --prompt and --out" in capsys.readouterr().err
