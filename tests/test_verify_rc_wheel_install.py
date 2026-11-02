"""Real offline pip-install fixture and failure gates; no production wheel claimed."""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import importlib.util
import os
from unittest import mock
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location("verify_rc_wheel_install", SCRIPTS / "verify_rc_wheel_install.py")
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


class InstallGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="midivolt-install-fixture-")
        cls.root = Path(cls.tmp.name)
        src = cls.root / "src/midivolt"
        src.mkdir(parents=True)
        (cls.root / "README.md").write_text("Synthetic test-only package. Not MIDIVOLT production.\n")
        (cls.root / "LICENSE").write_text("Apache-2.0 synthetic test license.\n")
        (cls.root / "THIRD_PARTY_NOTICES.md").write_text("Synthetic test notices.\n")
        (src / "__init__.py").write_text('__version__ = "0.1.0rc1"\n')
        declared = []
        for name in checker.EXPECTED_SCRIPTS:
            module = name.replace("midivolt-", "").replace("-", "_") if name != "midivolt" else "cli"
            if name == "midivolt-prompt": module = "prompt_cli"
            if name == "midivolt-ai": module = "ai_cli"
            if name == "midivolt-review": module = "review_cli"
            if name == "midivolt-transcribe": module = "transcribe"
            if name == "midivolt-evaluate": module = "evaluate"
            module += "" if module.endswith("_cli") or name in ("midivolt-transcribe", "midivolt-evaluate") else "_cli"
            if name == "midivolt": module = "cli"
            if name == "midivolt-hub": module = "model_hub_cli"
            if name == "midivolt-env": module = "environment_cli"
            if name == "midivolt-accept": module = "acceptance_cli"
            if name == "midivolt-model": module = "model_cli"
            (src / (module + ".py")).write_text("def main(argv=None):\n    return 0\n")
            declared.append(f'{name} = "midivolt.{module}:main"')
        (src / "helper.py").write_text("def util(): return 0\n")
        cls.project = cls.root / "pyproject.toml"
        cls.project.write_text('[build-system]\nrequires=["setuptools>=68","wheel"]\nbuild-backend="setuptools.build_meta"\n'
                '[project]\nname="midivolt"\nversion="0.1.0rc1"\nrequires-python=">=3.11,<3.14"\n'
                'description="fixture"\nreadme="README.md"\n'
                'license="Apache-2.0"\nlicense-files=["LICENSE","THIRD_PARTY_NOTICES.md"]\n'
                '[project.scripts]\n' + '\n'.join(declared) + '\n'
                '[tool.setuptools.packages.find]\nwhere=["src"]\n')
        cls.dist = cls.root / "dist"
        cls.dist.mkdir()
        result = subprocess.run([sys.executable, "-m", "pip", "wheel", "--no-deps", "--no-build-isolation",
                    "--ignore-requires-python", "-w", str(cls.dist), str(cls.root)], capture_output=True, text=True)
        if result.returncode:
            raise AssertionError(result.stdout[-1000:] + result.stderr[-2000:])
        cls.wheel = next(cls.dist.glob("*.whl"))
        cls.hash = sha256(cls.wheel.read_bytes()).hexdigest()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_real_pip_wheel_installs_and_loads_13_console_scripts_offline(self):
        result = checker.inspect_install(self.wheel, self.project, self.dist, self.hash,
                                         diagnostic_unsupported_python=True)
        supported = (3, 11) <= sys.version_info[:2] < (3, 14)
        self.assertEqual(result["status"], "PASS_SUPPORTED_PYTHON_INSTALL" if supported
                         else "PASS_DIAGNOSTIC_UNSUPPORTED_PYTHON", result)
        self.assertEqual(result["installed_cli_count"], 13)
        self.assertEqual(result["supported_runtime_certified"], supported)
        self.assertTrue(result["installation_attempted"])

    def test_inherited_pythonpath_metadata_does_not_skip_clean_install(self):
        # 回歸：PYTHONPATH 內已有 midivolt metadata 時，仍須真的安裝到乾淨 venv。
        with tempfile.TemporaryDirectory() as leak:
            info = Path(leak) / "midivolt.egg-info"
            info.mkdir()
            (info / "PKG-INFO").write_text("Metadata-Version: 2.1\nName: midivolt\nVersion: 0.1.0rc1\n")
            with mock.patch.dict(os.environ, {"PYTHONPATH": leak}):
                result = checker.inspect_install(self.wheel, self.project, self.dist, self.hash,
                                                 diagnostic_unsupported_python=True)
        self.assertEqual(result["installed_cli_count"], 13, result)
        self.assertEqual(result["errors"], [])

    def test_python_313_supported_by_new_core_policy(self):
        self.assertTrue(checker.supported_python(">=3.11,<3.14", (3, 13)))
        self.assertFalse(checker.supported_python(">=3.11,<3.12", (3, 13)))
        self.assertFalse(checker.supported_python(">=3.11,<3.14", (3, 14)))
        self.assertFalse(checker.supported_python("broken", (3, 13)))

    def test_unsupported_runtime_default_fails_closed(self):
        if (3, 11) <= sys.version_info[:2] < (3, 14): self.skipTest("Only checks unsupported-version mode")
        result = checker.inspect_install(self.wheel, self.project, self.dist, self.hash)
        self.assertIn("PYTHON_VERSION_OUTSIDE_PROJECT_RANGE", result["errors"])
        self.assertFalse(result["installation_attempted"])

    def test_bad_sha_rejects_before_install(self):
        result = checker.inspect_install(self.wheel, self.project, self.dist, "0" * 64,
                                         diagnostic_unsupported_python=True)
        self.assertIn("WHEEL_SHA256_MISMATCH", result["errors"])
        self.assertFalse(result["installation_attempted"])

    def test_missing_wheelhouse_rejects_before_install(self):
        result = checker.inspect_install(self.wheel, self.project, self.root / "missing", self.hash,
                                         diagnostic_unsupported_python=True)
        self.assertIn("MISSING_LOCAL_WHEEL_PROJECT_OR_WHEELHOUSE", result["errors"])
        self.assertFalse(result["installation_attempted"])

    def test_invalid_expected_digest_rejects(self):
        result = checker.inspect_install(self.wheel, self.project, self.dist, "invalid",
                                         diagnostic_unsupported_python=True)
        self.assertIn("INVALID_EXPECTED_SHA256", result["errors"])

    def test_wheel_source_mutation_rejects_before_install(self):
        target = self.root / "src/midivolt/helper.py"
        original = target.read_bytes()
        try:
            target.write_bytes(b"def util(): return 42\n")
            result = checker.inspect_install(self.wheel, self.project, self.dist, self.hash,
                                             diagnostic_unsupported_python=True)
            self.assertIn("WHEEL_SOURCE_OR_METADATA_INVALID", result["errors"])
            self.assertFalse(result["installation_attempted"])
        finally: target.write_bytes(original)


if __name__ == "__main__": unittest.main()
