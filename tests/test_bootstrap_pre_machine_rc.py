"""Bootstrap consent and safe preflight behavior; never downloads software."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("bootstrap_pre_machine_rc", ROOT / "scripts/bootstrap_pre_machine_rc.py")
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)

class TestBootstrap(unittest.TestCase):
    def test_run_parses_full_gate_json_before_truncation(self):
        import json
        from types import SimpleNamespace
        full = {"status": "PASS_PRE_MACHINE", "stages": {"details": "x" * 5000}}
        fake = SimpleNamespace(returncode=0, stdout=json.dumps(full) + "\n", stderr="")
        with patch.object(mod.subprocess, "run", return_value=fake):
            res = mod.run(["python", "gate"], {})
        self.assertEqual(res["json_result"], full)
        self.assertLess(len(res["stdout_tail"]), 1300)

    def test_nested_venv_keeps_same_python_version(self):
        # 回歸：外層 venv 內再建立 venv 時必須維持相同的 Python 版本。
        import subprocess
        with tempfile.TemporaryDirectory() as folder:
            outer, inner = Path(folder) / "outer", Path(folder) / "inner"
            mod.create_venv(outer, with_pip=False)
            py = outer / "bin" / "python"
            if not py.exists():
                self.skipTest("POSIX layout only")
            subprocess.run([str(py), "-c", "import venv,sys;venv.EnvBuilder().create(sys.argv[1])", str(inner)], check=True)
            version = lambda exe: subprocess.run([str(exe), "-c", "import sys;print(sys.version_info[:3])"],
                                                 capture_output=True, text=True, check=True).stdout
            self.assertEqual(version(inner / "bin" / "python"), version(py))

    def test_network_not_implicit(self):
        with patch.object(mod, "run") as run:
            r = mod.bootstrap()
        self.assertEqual(r["reason"], "PROVIDE_TRUSTED_WHEELHOUSE_OR_ALLOW_NETWORK")
        run.assert_not_called()

    def test_network_and_offline_mutually_exclusive(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(mod, "run") as run:
                r = mod.bootstrap(allow_network=True, wheelhouse=Path(folder))
        self.assertEqual(r["reason"], "CHOOSE_NETWORK_OR_OFFLINE_NOT_BOTH")
        run.assert_not_called()

    def test_invalid_offline_wheelhouse_never_executes(self):
        with patch.object(mod, "run") as run:
            r = mod.bootstrap(wheelhouse=Path("/missing/path/midivolt-wheelhouse"))
        self.assertEqual(r["reason"], "INVALID_TRUSTED_WHEELHOUSE")
        run.assert_not_called()

    def test_git_head_missing_blocks_before_download(self):
        with patch.object(mod, "run", return_value={"status": "FAIL", "stdout_tail": ""}) as run:
            r = mod.bootstrap(allow_network=True)
        self.assertEqual(r["reason"], "UNVERIFIED_GIT_HEAD")
        self.assertEqual(run.call_count, 1)

    def test_python313_blocks_full_suite_before_network_download(self):
        sha = "a" * 40
        with patch.object(mod, "run", side_effect=[
            {"status": "PASS", "stdout_tail": sha},
            {"status": "PASS", "stdout_tail": ""}
        ]) as command, patch.object(mod.sys, "version_info", (3, 13, 5)):
            result = mod.bootstrap(allow_network=True)
        self.assertEqual(result["reason"], "PYTHON311_REQUIRED_FOR_FULL_PRODUCT_SUITE")
        self.assertEqual(command.call_count, 2)

    def test_python311_progresses_to_download_when_checkout_clean(self):
        sha = "b" * 40
        with patch.object(mod, "run", side_effect=[
            {"status": "PASS", "stdout_tail": sha},
            {"status": "PASS", "stdout_tail": ""},
            {"status": "FAIL", "exit_code": 1, "stderr_tail": "network blocked"},
        ]) as command, patch.object(mod.sys, "version_info", (3, 11, 9)):
            result = mod.bootstrap(allow_network=True)
        self.assertEqual(result["reason"], "DEPENDENCY_DOWNLOAD_OR_BUILD_FAILED")
        self.assertEqual(command.call_count, 3)

    def test_dirty_checkout_blocks_before_download(self):
        sha = "a" * 40
        with patch.object(mod, "run", side_effect=[
            {"status": "PASS", "stdout_tail": sha},
            {"status": "PASS", "stdout_tail": "?? untracked.txt\n"}
        ]) as run:
            r = mod.bootstrap(allow_network=True)
        self.assertEqual(r["reason"], "DIRTY_GIT_CHECKOUT")
        self.assertEqual(run.call_count, 2)

if __name__ == "__main__": unittest.main()
