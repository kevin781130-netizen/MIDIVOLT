"""Run genuine setuptools/pip Wheel build against SHA-verified 40-file fixture."""
from __future__ import annotations

from hashlib import sha1, sha256
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from zipfile import ZipFile

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import build_verified_wheel_offline as builder


TEST_SOURCE_COMMIT = "a" * 40


class WheelBuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="midivolt-setuptools-fixture-")
        cls.root = Path(cls.temp.name)
        cls.chunks = cls.root / "source_transport"
        cls.chunks.mkdir()
        files = {x: "Fixture; not production source.\n" for x in (
            "README.md", "LICENSE", "THIRD_PARTY_NOTICES.md")}
        cli_modules = ["cli", "prompt_cli", "ai_cli", "bridge_cli", "tsov_cli",
                       "review_cli", "model_cli", "model_hub_cli", "environment_cli",
                       "acceptance_cli", "cubase_cli", "transcribe", "evaluate"]
        cli_names = ["midivolt", "midivolt-prompt", "midivolt-ai", "midivolt-bridge",
                     "midivolt-tsov", "midivolt-review", "midivolt-model", "midivolt-hub",
                     "midivolt-env", "midivolt-accept", "midivolt-cubase",
                     "midivolt-transcribe", "midivolt-evaluate"]
        scripts = list(zip(cli_names, cli_modules))
        files["pyproject.toml"] = ('[build-system]\nrequires=["setuptools>=68","wheel"]\n'
                                    'build-backend="setuptools.build_meta"\n'
                                    '[project]\nname="midivolt"\nversion="0.1.0rc1"\n'
                                    'description="fixture"\nreadme="README.md"\n'
                                    'requires-python=">=3.11,<3.12"\n'
                                    '[project.scripts]\n' +
                                    ''.join(f'{name}="midivolt.{mod}:main"\n' for name,mod in scripts) +
                                    '[tool.setuptools.packages.find]\nwhere=["src"]\n')
        files["src/midivolt/__init__.py"] = '__version__ = "0.1.0rc1"\n'
        for i, mod in enumerate(cli_modules):
            files[f"src/midivolt/{mod}.py"] = f"def main():\n    return {i}\n"
        for i in range(36-14):
            files[f"src/midivolt/extra{i:02d}.py"] = f"def helper(): return {i}\n"
        assert len(files) == 40
        cls.files = files
        chunks=[];inventory=[]
        for i in range(6):
            selected=sorted(files)[7*i:7*(i+1)]
            batch={"source_tree":TEST_SOURCE_COMMIT, "files":[]}
            for name in selected:
                content=files[name]
                blob=builder.load_snapshot.__globals__["git_blob_sha"](content.encode())
                batch["files"].append({"path":name,"sha":blob,"content":content})
                inventory.append({"path":name,"git_blob_sha":blob,"chunk":i})
            p=cls.chunks/f"part-{i:02d}.json"
            p.write_text(json.dumps(batch,separators=(",",":")),encoding="utf-8")
            chunks.append({"path":f"source_transport/part-{i:02d}.json",
                           "git_blob_sha":builder.load_snapshot.__globals__["git_blob_sha"](p.read_bytes()),
                           "files":len(selected)})
        cls.manifest={"format":"midivolt-offline-source-snapshot-v1",
                      "source_commit":TEST_SOURCE_COMMIT,"source_blob_count":40,
                      "package_module_count":36,"chunks":chunks,"files":inventory}
        cls.manifest_path=cls.chunks/"MANIFEST.json"
        cls.manifest_path.write_text(json.dumps(cls.manifest),encoding="utf-8")
        cls.output=cls.root/"dist"
        cls.output.mkdir()
        cls.result=builder.build_verified(cls.root,cls.output,diagnostic=True,
                                            expected_source_commit=TEST_SOURCE_COMMIT)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_actual_setuptools_build_produces_valid_wheel(self):
        self.assertEqual(self.result["status"],"PASS_DIAGNOSTIC_WHEEL_BUILD",self.result)
        self.assertTrue(self.result["built"])
        self.assertEqual(self.result["source_modules"],36)
        self.assertEqual(self.result["cli_entries"],13)
        path=Path(self.result["wheel"])
        self.assertEqual(self.result["sha256"],sha256(path.read_bytes()).hexdigest())
        with ZipFile(path) as z:
            self.assertIn("midivolt/extra21.py",z.namelist())

    def test_no_python_311_defaults_to_block(self):
        if sys.version_info[:2] == (3,11): self.skipTest("requires unsupported runtime")
        d=builder.build_verified(self.root,self.output)
        self.assertEqual(d["errors"],["PYTHON_3_11_REQUIRED"])
        self.assertFalse(d["built"])

    def test_refuses_overwriting_previous_wheel(self):
        r=builder.build_verified(self.root,self.output,diagnostic=True,
                                            expected_source_commit=TEST_SOURCE_COMMIT)
        self.assertTrue(any("OUTPUT_EXISTS_REFUSE_OVERWRITE" in e for e in r["errors"]),r)

    def test_rejects_invalid_snapshot_chunk(self):
        p=self.chunks/"part-03.json"
        before=p.read_bytes()
        try:
            p.write_bytes(before+b"\n")
            r=builder.build_verified(self.root,self.output,diagnostic=True,
                                            expected_source_commit=TEST_SOURCE_COMMIT)
            self.assertTrue(any("SHA mismatch in source chunk" in e for e in r["errors"]),r)
        finally: p.write_bytes(before)

    def test_rejects_absent_output_directory(self):
        r=builder.build_verified(self.root,self.root/"absent",diagnostic=True,
                                            expected_source_commit=TEST_SOURCE_COMMIT)
        self.assertEqual(r["errors"],["OUTPUT_DIRECTORY_REQUIRED"])

    def test_record_catches_source_modification(self):
        with tempfile.TemporaryDirectory() as d:
            src=Path(d)
            for name,contents in self.files.items():
                path=src/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(contents)
            (src/"src/midivolt/extra02.py").write_text("def helper(): return -123\n")
            with self.assertRaisesRegex(builder.BuildGateError,"Missing or modified source"):
                builder.check_wheel(Path(self.result["wheel"]),src)

    def test_record_catches_corrupted_zip_member(self):
        with tempfile.TemporaryDirectory() as d:
            src=Path(d)
            for name,contents in self.files.items():
                path=src/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(contents)
            with ZipFile(self.result["wheel"]) as z:
                import io
                files={name:z.read(name) for name in z.namelist()}
            files["midivolt/extra02.py"]=b"def helper(): return -2\n"
            invalid=src/"broken.whl"
            with ZipFile(invalid,"w") as z:
                for name,content in files.items(): z.writestr(name,content)
            with self.assertRaisesRegex(builder.BuildGateError,"Missing or modified source"):
                builder.check_wheel(invalid,src)

    def test_source_commit_substitution_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            result = builder.build_verified(self.root, output, diagnostic=True,
                                            expected_source_commit="b" * 40)
            self.assertIn("SOURCE_COMMIT_MISMATCH", result["errors"])
            self.assertFalse(result["built"])
            self.assertFalse(list(output.glob("*.whl")))

    def test_malformed_expected_commit_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            result = builder.build_verified(self.root, Path(temp), diagnostic=True,
                                            expected_source_commit="bad")
            self.assertEqual(result["errors"], ["INVALID_EXPECTED_SOURCE_COMMIT"])
            self.assertFalse(result["built"])

    def test_snapshot_verify_refuses_untrusted_content(self):
        m=self.chunks/"MANIFEST.json"
        original=m.read_bytes()
        try:
            malformed=json.loads(original)
            malformed["files"][1]["git_blob_sha"]="0"*40
            m.write_text(json.dumps(malformed))
            r=builder.build_verified(self.root,self.output,diagnostic=True,
                                            expected_source_commit=TEST_SOURCE_COMMIT)
            self.assertTrue(any("Source manifest SHA mismatch" in e for e in r["errors"]),r)
        finally:m.write_bytes(original)


if __name__=="__main__":unittest.main()
