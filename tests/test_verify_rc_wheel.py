"""Real pip-built wheel fixture, plus deliberate corruption regressions."""
from __future__ import annotations

import csv
from io import StringIO
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from zipfile import ZipFile, ZIP_DEFLATED

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/verify_rc_wheel.py"
spec = importlib.util.spec_from_file_location("verify_rc_wheel", SCRIPT)
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)


class WheelVerifierTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.project = cls.root / "pyproject.toml"
        target_dir = cls.root / "src/midivolt"
        target_dir.mkdir(parents=True)
        (cls.root / "README.md").write_text("Fixture, not MIDIVOLT production code.\n")
        (target_dir / "__init__.py").write_text('__version__ = "0.1.0rc1"\n')
        programs = ["cli", "prompt_cli", "ai_cli", "bridge_cli", "tsov_cli", "review_cli", "model_cli", "model_hub_cli", "environment_cli", "acceptance_cli", "cubase_cli", "transcribe", "evaluate"]
        (target_dir / "internal_helper.py").write_text("def helper(): return True\n")
        entrypoints = []
        for x in programs:
            (target_dir / (x + ".py")).write_text("def main(argv=None):\n    return 0\n")
            entrypoints.append(f'midivolt-{x} = "midivolt.{x}:main"')
        cls.project.write_text('[build-system]\nrequires = ["setuptools>=68", "wheel"]\nbuild-backend = "setuptools.build_meta"\n'
                               '[project]\nname = "midivolt"\nversion = "0.1.0rc1"\nrequires-python = ">=3.11,<3.12"\n'
                               'description = "fixture"\nreadme = "README.md"\n[project.scripts]\n' + '\n'.join(entrypoints) + '\n'
                               '[tool.setuptools.packages.find]\nwhere = ["src"]\n')
        result = subprocess.run([sys.executable, "-m", "pip", "wheel", "--no-deps", "--no-build-isolation", "--ignore-requires-python", "-w", str(cls.root / "dist"), str(cls.root)], capture_output=True, text=True, check=False)
        if result.returncode:
            raise AssertionError("Could not build fixture wheel:\n" + result.stderr[-1500:])
        cls.wheel = next((cls.root / "dist").glob("*.whl"))
        cls.entries = {}
        with ZipFile(cls.wheel) as z:
            for n in z.namelist(): cls.entries[n] = z.read(n)
        cls.dist = next(x for x in cls.entries if x.endswith(".dist-info/RECORD")).split(".dist-info/")[0] + ".dist-info/"

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def mutate(self, changes=None, deletes=(), extras=None):
        files = dict(self.entries)
        for key in deletes: files.pop(key, None)
        files.update(changes or {})
        files.update(extras or {})
        target = self.root / ("broken_" + str(len(list(self.root.glob('broken*')))) + ".whl")
        with ZipFile(target, "w", ZIP_DEFLATED) as z:
            for k, v in files.items(): z.writestr(k, v)
        return target

    def check(self, wheel=None):
        return verifier.inspect_wheel(wheel or self.wheel, self.project)

    def test_real_pip_built_fixture_wheel_passes(self):
        output = self.check()
        self.assertEqual(output["status"], "PASS_WHEEL_INTEGRITY_NOT_INSTALLATION", output["errors"])
        self.assertFalse(output["python_runtime_certified"])

    def test_real_fixture_wheel_installs_without_network(self):
        # A genuine pip install against a disposable fixture, NOT MIDIVOLT code.
        target = self.root / "offline-installed"
        res = subprocess.run([sys.executable, "-m", "pip", "install", "--no-index",
                              "--ignore-requires-python", "--no-deps", "--target",
                              str(target), str(self.wheel)], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, res.stderr[-1200:])
        check = subprocess.run([sys.executable, "-c",
                                "import sys;sys.path.insert(0,sys.argv[1]);"
                                "import midivolt.cli;assert midivolt.cli.main()==0" , str(target)],
                               capture_output=True, text=True)
        self.assertEqual(check.returncode, 0, check.stderr)

    def test_missing_entrypoint_module_fails(self):
        output = self.check(self.mutate(deletes=["midivolt/ai_cli.py"]))
        self.assertIn("MISSING_ENTRYPOINT_MODULE:midivolt-ai_cli", output["errors"])

    def test_non_cli_source_omission_is_rejected(self):
        output = self.check(self.mutate(deletes=["midivolt/internal_helper.py"]))
        self.assertIn("MISSING_PACKAGED_SOURCE:midivolt/internal_helper.py", output["errors"])

    def test_forged_source_without_matching_wheel_fails(self):
        helper = self.root / "src/midivolt/internal_helper.py"
        before = helper.read_bytes()
        self.addCleanup(helper.write_bytes, before)
        helper.write_bytes(b"def helper(): return False\n")
        output = self.check()
        self.assertIn("PACKAGED_SOURCE_MISMATCH:midivolt/internal_helper.py", output["errors"])

    def test_modified_module_digest_fails(self):
        output = self.check(self.mutate(changes={"midivolt/ai_cli.py": b"def main(): return 99\n"}))
        self.assertTrue(any(x.startswith("RECORD_DIGEST_OR_SIZE_MISMATCH:") for x in output["errors"]))

    def test_missing_entry_point_registration_fails(self):
        name = self.dist + "entry_points.txt"
        entrypoints = self.entries[name].replace(b"midivolt-ai_cli = midivolt.ai_cli:main\n", b"")
        output = self.check(self.mutate(changes={name: entrypoints}))
        self.assertIn("ENTRYPOINTS_MISMATCH", output["errors"])

    def test_wrong_requires_python_fails(self):
        name = self.dist + "METADATA"
        meta = self.entries[name].replace(b"Requires-Python: <3.12,>=3.11", b"Requires-Python: >=3.13")
        self.assertNotEqual(meta, self.entries[name])
        output = self.check(self.mutate(changes={name: meta}))
        self.assertIn("PYTHON_RUNTIME_MISMATCH", output["errors"])

    def test_zip_path_traversal_fails(self):
        output = self.check(self.mutate(extras={"../oops.py": b"pass"}))
        self.assertIn("UNSAFE_ARCHIVE_PATH", output["errors"])

    def test_missing_record_member_fails(self):
        missing = "midivolt/prompt_cli.py"
        output = self.check(self.mutate(deletes=[missing]))
        self.assertIn("RECORD_REFERENCES_MISSING_FILE", output["errors"])

    def test_invalid_record_format_fails(self):
        name = self.dist + "RECORD"
        output = self.check(self.mutate(changes={name: b"not,a,valid,record\n"}))
        self.assertIn("INVALID_RECORD_ROW", output["errors"])


if __name__ == "__main__":
    unittest.main()
