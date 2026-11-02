"""Standard-library-only negative-path checks for MIDIVOLT pre-build contract."""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
import importlib.util

script = Path(__file__).resolve().parents[1] / "scripts/verify_rc_source_contract.py"
spec = importlib.util.spec_from_file_location("verify_rc_source_contract", script)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class SourceContractTests(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory()
        self.addCleanup(self.work.cleanup)
        self.root = Path(self.work.name)
        self.write("pyproject.toml", '''[build-system]\nrequires = ["setuptools>=68", "wheel"]\nbuild-backend = "setuptools.build_meta"\n[project]\nname="midivolt"\nversion="0.1.0rc1"\nrequires-python=">=3.11,<3.14"\nlicense="Apache-2.0"\nlicense-files=["LICENSE","THIRD_PARTY_NOTICES.md"]\n[project.scripts]\n''' + "\n".join(f'midivolt-{i}="midivolt.cli{i}:main"' for i in range(13)))
        self.write("src/midivolt/__init__.py", '__version__ = "0.1.0rc1"\n')
        for i in range(13):
            self.write(f"src/midivolt/cli{i}.py", "def main(argv=None):\n    return 0\n")
        for x in mod.REQUIRED_ASSETS: self.write(x, "present\n")
        self.write("packaging/windows/Install-MIDIVOLT.ps1", "AllowNetwork Wheelhouse --no-index already exists Smoke-MIDIVOLT.ps1")
        self.write("packaging/windows/Smoke-MIDIVOLT.ps1", " ".join(f'"{v}"' for v in ("midivolt", "midivolt-hub", "midivolt-review", "midivolt-cubase", "midivolt-model", "midivolt-env", "midivolt-accept", "midivolt-tsov", "midivolt-bridge")) + " WINDOWS_RC_SMOKE=PASS")
        # Make declared CLI names compatible with release requirements.
        self.write("pyproject.toml", (self.root / "pyproject.toml").read_text().replace('midivolt-0=', 'midivolt=').replace('midivolt-1=', 'midivolt-hub=').replace('midivolt-2=', 'midivolt-review=').replace('midivolt-3=', 'midivolt-cubase=').replace('midivolt-4=', 'midivolt-model=').replace('midivolt-5=', 'midivolt-env=').replace('midivolt-6=', 'midivolt-accept=').replace('midivolt-7=', 'midivolt-tsov=').replace('midivolt-8=', 'midivolt-bridge='))
        self.write(".github/workflows/windows-rc.yml", "python -m build --wheel\nCompress-Archive\nGet-FileHash -Algorithm SHA256\nCopy-Item LICENSE\nCopy-Item THIRD_PARTY_NOTICES.md\n" + "\n".join(mod.REQUIRED_ASSETS[:3]))

    def write(self, name, content):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def test_valid_source_is_prebuild_pass_not_runtime_pass(self):
        result = mod.inspect(self.root)
        self.assertEqual(result["status"], "PASS_SOURCE_CONTRACT_NOT_RUNTIME", result["errors"])
        self.assertFalse(result["python_runtime_certified"])
        self.assertFalse(result["wheel_built"])

    def test_missing_console_module_is_rejected(self):
        (self.root / "src/midivolt/cli2.py").unlink()
        self.assertIn("MISSING_OR_UNSAFE:src/midivolt/cli2.py", mod.inspect(self.root)["errors"])

    def test_missing_callable_is_rejected(self):
        self.write("src/midivolt/cli2.py", "def wrong():\n    pass\n")
        self.assertIn("MISSING_ENTRYPOINT_FUNCTION:midivolt-review", mod.inspect(self.root)["errors"])

    def test_empty_entrypoint_module_is_rejected(self):
        self.write("src/midivolt/cli2.py", "")
        self.assertIn("EMPTY_ENTRYPOINT_MODULE:src/midivolt/cli2.py", mod.inspect(self.root)["errors"])

    def test_python_support_policy_mismatch_is_rejected(self):
        p = self.root / "pyproject.toml"
        p.write_text(p.read_text().replace(">=3.11,<3.14", ">=3.13"))
        self.assertIn("RUNTIME_CONTRACT_MISMATCH", mod.inspect(self.root)["errors"])

    def test_missing_license_file_declaration_is_rejected(self):
        p = self.root / "pyproject.toml"
        p.write_text(p.read_text().replace('license-files=["LICENSE","THIRD_PARTY_NOTICES.md"]', 'license-files=["LICENSE"]'))
        self.assertIn("LICENSE_SOURCE_METADATA_MISMATCH", mod.inspect(self.root)["errors"])

    def test_missing_licensing_notice_is_rejected(self):
        (self.root / "THIRD_PARTY_NOTICES.md").unlink()
        self.assertIn("MISSING_OR_UNSAFE:THIRD_PARTY_NOTICES.md", mod.inspect(self.root)["errors"])

    def test_installer_offline_policy_regression_is_rejected(self):
        self.write("packaging/windows/Install-MIDIVOLT.ps1", "AllowNetwork Wheelhouse already exists Smoke-MIDIVOLT.ps1")
        self.assertIn("INSTALLER_CONTRACT_MISSING:--no-index", mod.inspect(self.root)["errors"])

    def test_source_path_symlink_outside_root_is_rejected(self):
        target = self.root / "src/midivolt/cli2.py"
        target.unlink()
        external = self.root.parent / (self.root.name + "-external.py")
        external.write_text("def main(): pass")
        self.addCleanup(external.unlink)
        try: target.symlink_to(external)
        except (OSError, NotImplementedError): self.skipTest("symlink disabled")
        self.assertIn("MISSING_OR_UNSAFE:src/midivolt/cli2.py", mod.inspect(self.root)["errors"])


if __name__ == "__main__": unittest.main()
