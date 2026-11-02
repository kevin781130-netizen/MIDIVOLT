"""Isolated end-to-end tests for AI release-gate control flow; fixtures are not production AI tests."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

SOURCE_ROOT = Path(__file__).resolve().parents[1]
REQUIRED = (
    "test_ai_provider_to_review_e2e.py",
    "test_review_engine.py",
    "test_approval_snapshot_standalone.py",
    "test_candidate_cleanup_standalone.py",
    "test_provider_contract_standalone.py",
)


class AIGateProcessTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="midivolt-gate-process-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        for folder in ("scripts", "tests", "src"):
            (self.root / folder).mkdir()
        shutil.copyfile(SOURCE_ROOT / "scripts/verify_ai_offline.py",
                        self.root / "scripts/verify_ai_offline.py")
        shutil.copyfile(SOURCE_ROOT / "pyproject.toml", self.root / "pyproject.toml")
        for i, name in enumerate(REQUIRED):
            (self.root / "tests" / name).write_text(
                "\n".join(f"def test_fixture_{i}_{n}(): assert True" for n in range(8)) + "\n",
                encoding="utf-8")

    def invoke(self):
        result = subprocess.run(
            [sys.executable, str(self.root / "scripts/verify_ai_offline.py")],
            cwd=self.root, text=True, capture_output=True, timeout=45)
        self.assertTrue(result.stdout.strip(), result.stderr)
        return result.returncode, json.loads(result.stdout.strip().splitlines()[-1])

    def test_supported_runtime_reports_pass_for_complete_synthetic_fixture(self):
        if not (3, 11) <= sys.version_info[:2] < (3, 14):
            self.skipTest("Only core-supported Python may certify this gate")
        code, report = self.invoke()
        self.assertEqual(code, 0)
        self.assertEqual(report["status"], "PASS_SUPPORTED_RUNTIME")
        self.assertEqual(report["suite"], {"tests": 40, "failures": 0, "errors": 0, "skipped": 0})

    def test_missing_required_suite_blocks_before_pytest(self):
        (self.root / "tests" / REQUIRED[0]).unlink()
        code, report = self.invoke()
        self.assertEqual((code, report["status"]), (4, "BLOCKED_MISSING_TEST_FILES"))

    def test_unknown_python_policy_blocks_before_pytest(self):
        pyproject = self.root / "pyproject.toml"
        pyproject.write_text(pyproject.read_text(encoding="utf-8").replace(
            'requires-python = ">=3.11,<3.14"', 'requires-python = ">=3.11"'), encoding="utf-8")
        code, report = self.invoke()
        self.assertEqual((code, report["status"]), (4, "BLOCKED_PROJECT_POLICY"))


if __name__ == "__main__":
    unittest.main()
