"""Negative-path regression for the pre-machine RC gate; no real release claimed."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/verify_pre_machine_rc.py"
spec = importlib.util.spec_from_file_location("verify_pre_machine_rc", SCRIPT)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


class PreMachineGateTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="midivolt-rc-negative-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.patcher = patch.object(gate, "ROOT", self.root)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def project(self, policy=">=3.11,<3.14"):
        (self.root / "pyproject.toml").write_text(
            f'[project]\nname="midivolt"\nrequires-python="{policy}"\n', encoding="utf-8")

    def test_missing_project_blocks(self):
        r = gate.release_gate(None)
        self.assertEqual((r["status"], r["reason"]), ("BLOCKED", "MISSING_OR_INVALID_PROJECT"))

    def test_wrong_python_policy_blocks(self):
        self.project(">=3.11")
        r = gate.release_gate(None)
        self.assertEqual((r["status"], r["reason"]), ("BLOCKED", "INVALID_CORE_PYTHON_POLICY"))

    def test_source_contract_failure_stops_pipeline(self):
        self.project()
        with patch.object(gate, "run_command", return_value={"status": "FAIL", "exit_code": 2}) as cmd:
            r = gate.release_gate(None)
        self.assertEqual(r["reason"], "STOP_AT_SOURCE_CONTRACT")
        self.assertEqual(cmd.call_count, 1)

    def test_ai_failure_stops_before_music21_and_build(self):
        self.project()
        values = [{"status": "PASS", "stdout_tail": ""}, {"status": "PASS", "stdout_tail": ""},
                  {"status": "FAIL", "exit_code": 1}]
        with patch.object(gate, "run_command", side_effect=values) as cmd:
            r = gate.release_gate(None)
        self.assertEqual(r["reason"], "STOP_AT_AI_REGRESSION")
        self.assertEqual(cmd.call_count, 3)

    def test_music21_requires_real_success_marker(self):
        self.project()
        values = [{"status": "PASS", "stdout_tail": ""}, {"status": "PASS", "stdout_tail": ""},
                  {"status": "PASS", "stdout_tail": "PASS_SUPPORTED_RUNTIME"},
                  {"status": "PASS", "stdout_tail": "a different status"}]
        with patch.object(gate, "run_command", side_effect=values) as cmd:
            r = gate.release_gate(None)
        self.assertEqual(r["reason"], "MUSIC21_SUCCESS_MARKER_MISSING")
        self.assertEqual(cmd.call_count, 4)

    def test_expected_head_rejects_mismatch_before_checks(self):
        self.project()
        with patch.object(gate, "run_command",
                          return_value={"status": "PASS", "stdout_tail": "not-expected"}) as cmd:
            r = gate.release_gate(None, "0" * 40)
        self.assertEqual(r["reason"], "CHECKOUT_HEAD_MISMATCH")
        self.assertEqual(cmd.call_count, 1)

    def test_invalid_expected_head_blocks_before_git(self):
        self.project()
        with patch.object(gate, "run_command") as cmd:
            result = gate.release_gate(None, "not-a-40-character-sha")
        self.assertEqual(result["reason"], "INVALID_EXPECTED_HEAD")
        cmd.assert_not_called()

    def test_dirty_checkout_blocks_before_product_tests(self):
        self.project()
        sha = "a" * 40
        values = [{"status": "PASS", "stdout_tail": sha},
                  {"status": "PASS", "stdout_tail": " M src/midivolt/ai_cli.py\n"}]
        with patch.object(gate, "run_command", side_effect=values) as cmd:
            result = gate.release_gate(None, sha)
        self.assertEqual(result["reason"], "CHECKOUT_DIRTY_OR_UNVERIFIED")
        self.assertEqual(cmd.call_count, 2)

    def test_wheel_build_failure_blocks_after_all_real_test_markers(self):
        self.project()
        values = [{"status": "PASS", "stdout_tail": ""}, {"status": "PASS", "stdout_tail": ""},
                  {"status": "PASS", "stdout_tail": "PASS_SUPPORTED_RUNTIME"},
                  {"status": "PASS", "stdout_tail": "PASS_REAL_MUSIC21_ACCEPTANCE"},
                  {"status": "FAIL", "exit_code": 1}]
        with patch.object(gate, "run_command", side_effect=values) as cmd:
            r = gate.release_gate(None)
        self.assertEqual(r["reason"], "STOP_AT_WHEEL_BUILD")
        self.assertEqual(cmd.call_count, 5)


if __name__ == "__main__":
    unittest.main()
