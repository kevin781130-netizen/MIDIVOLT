"""Model Hub smoke tests: no live Hugging Face requests, no model execution."""
from hashlib import sha1, sha256
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from midivolt.model_hub import (
    CATALOG, ModelHubError, catalog, doctor, download_asset,
    inspect_model, search_models,
)
from midivolt.model_hub_cli import main


REV = "a" * 40
DATA = b"sample model config\n"


def blob_digest(data):
    return sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


def api_for(filename="config.json", data=DATA, *,
            with_lfs=False, license_name="apache-2.0",
            size=None, sha=None):
    digest = sha256(data).hexdigest()
    remote = NS(
        sha=sha or REV, card_data={"license": license_name},
        siblings=[NS(
            rfilename=filename,
            size=len(data) if size is None else size,
            lfs={"sha256": digest, "size": len(data)} if with_lfs else {},
            blob_id=blob_digest(data),
        )],
    )
    class FakeAPI:
        calls = 0
        def model_info(self, repo_id, *, revision=None, files_metadata=False):
            self.calls += 1
            assert repo_id in (v.repo_id for v in CATALOG.values())
            assert files_metadata is True
            return remote
        def list_models(self, *, search, limit, full):
            self.calls += 1
            return [
                NS(id="example/unknown-midi-model", sha=REV,
                   card_data={"license": "unknown"}, pipeline_tag="text-to-music"),
                NS(id=CATALOG["anticipation"].repo_id, sha=REV,
                   card_data={"license": "apache-2.0"}, pipeline_tag="text-generation"),
            ][:limit]
    return FakeAPI()


def fake_download(data=DATA):
    def fetch(*, repo_id, filename, revision, local_dir, token):
        assert repo_id == CATALOG["anticipation"].repo_id
        assert revision == REV and token is False
        assert filename == "config.json"
        path = Path(local_dir) / filename
        path.write_bytes(data)
        return str(path)
    return fetch


def test_catalog_requires_no_network(capsys):
    assert len(catalog()) == 2
    assert len(catalog("conditional")) == 1
    assert main(["catalog"]) == 0
    assert "network_used" in capsys.readouterr().out


def test_offline_inspect_no_remote_version_claim():
    info = inspect_model("text2midi")
    assert info["revision"] is None
    assert info["metadata_source"] == "offline_catalog"
    assert info["license_verified_online"] is False


def test_online_inspect_returns_immutable_revision_and_allowlist():
    api = api_for(filename="config.json")
    result = inspect_model("anticipation", online=True, api=api)
    assert api.calls == 1
    assert result["revision"] == REV
    assert result["license_verified_online"] is True
    assert result["available_assets"][0]["filename"] == "config.json"
    assert "pytorch_model.bin" in result["missing_assets"]


def test_remote_search_only_when_online():
    api = api_for()
    offline = search_models("midi", api=api)
    assert api.calls == 0 and offline["network_used"] is False
    online = search_models("midi", online=True, api=api)
    assert api.calls == 1 and len(online["remote"]) == 2
    assert online["remote"][0]["download_supported"] is False
    assert online["remote"][1]["curated"] is True


def test_permission_gate_is_before_network(tmp_path):
    api = api_for()
    params = dict(key="anticipation", filename="config.json",
                  revision=REV, destination=tmp_path,
                  api=api, downloader=fake_download())
    with pytest.raises(PermissionError, match="confirm"):
        download_asset(**params)
    with pytest.raises(PermissionError, match="license"):
        download_asset(**params, confirm=True)
    with pytest.raises(ValueError, match="allowlist"):
        download_asset(**{**params, "filename": "bad/../../file"}, confirm=True)
    with pytest.raises(ValueError, match="40-character"):
        download_asset(**{**params, "revision": "main"}, confirm=True)
    assert api.calls == 0
    assert list(tmp_path.iterdir()) == []


def test_download_single_verified_metadata_file(tmp_path):
    api = api_for()
    result = download_asset(
        "anticipation", "config.json", REV, tmp_path,
        confirm=True, accept_license="apache-2.0", api=api,
        downloader=fake_download())
    assert result["sha256"] == sha256(DATA).hexdigest()
    assert (tmp_path / "config.json").read_bytes() == DATA
    assert not any(p.name.startswith(".midivolt-hub") for p in tmp_path.iterdir())
    with pytest.raises(FileExistsError):
        download_asset(
            "anticipation", "config.json", REV, tmp_path,
            confirm=True, accept_license="apache-2.0", api=api,
            downloader=fake_download())


def test_corrupt_download_never_published(tmp_path):
    api = api_for()
    with pytest.raises(ModelHubError, match="Checksum"):
        download_asset(
            "anticipation", "config.json", REV, tmp_path,
            confirm=True, accept_license="apache-2.0",
            api=api, downloader=fake_download(b"x" * len(DATA)))
    assert not (tmp_path / "config.json").exists()


def test_license_change_and_revision_mismatch_fail(tmp_path):
    for client in (api_for(license_name="other-license"),
                   api_for(sha="b" * 40)):
        with pytest.raises(ModelHubError):
            download_asset(
                "anticipation", "config.json", REV, tmp_path,
                confirm=True, accept_license="apache-2.0",
                api=client, downloader=fake_download())
    assert not list(tmp_path.iterdir())


def test_excessive_file_size_is_rejected(tmp_path):
    api = api_for(size=3_000_000_000)
    with pytest.raises(ModelHubError, match="size"):
        download_asset(
            "anticipation", "config.json", REV, tmp_path,
            confirm=True, accept_license="apache-2.0",
            max_bytes=2_000_000_000,
            api=api, downloader=fake_download())
    assert not list(tmp_path.iterdir())


def test_pickle_requires_extra_ack_without_network(tmp_path):
    api = api_for(filename="pytorch_model.bin")
    with pytest.raises(PermissionError, match="allow-unsafe-format"):
        download_asset("anticipation", "pytorch_model.bin", REV, tmp_path,
                       confirm=True, accept_license="apache-2.0", api=api)
    assert api.calls == 0


def test_doctor_is_read_only_and_checks_expected_paths(tmp_path):
    src = tmp_path / "Text2midi"
    (src / "model").mkdir(parents=True)
    (src / "model" / "transformer_model.py").write_text("# checked")
    python = tmp_path / "python.exe"
    python.write_text("")
    checkpoint = tmp_path / "weights.bin"
    checkpoint.write_bytes(b"dummy")
    vocab = tmp_path / "vocab_remi.pkl"
    vocab.write_bytes(b"dummy")
    t5 = tmp_path / "tokenizer"
    t5.mkdir()
    result = doctor("text2midi", python=str(python), checkout=str(src),
                    checkpoint=str(checkpoint), vocab=str(vocab), t5_dir=str(t5))
    assert result["ready_for_runtime_smoke"]
    assert not result["runtime_inference_verified"]
    assert not doctor("anticipation")["ready_for_runtime_smoke"]


def test_prevents_unknown_models_and_untrusted_search():
    with pytest.raises(ValueError):
        inspect_model("other", online=True)
    with pytest.raises(ValueError):
        search_models("")
    with pytest.raises(ValueError):
        search_models("midi", limit=999)


def test_lfs_sha256_takes_priority_over_git_pointer_blob(tmp_path):
    api = api_for(filename="config.json", with_lfs=True)
    original = api.model_info
    def response(repo_id, *, revision=None, files_metadata=False):
        info = original(repo_id, revision=revision, files_metadata=files_metadata)
        info.siblings[0].blob_id = "b" * 40  # LFS pointer != downloaded payload
        return info
    api.model_info = response
    result = download_asset(
        "anticipation", "config.json", REV, tmp_path,
        confirm=True, accept_license="apache-2.0",
        api=api, downloader=fake_download())
    assert result["sha256"] == sha256(DATA).hexdigest()
