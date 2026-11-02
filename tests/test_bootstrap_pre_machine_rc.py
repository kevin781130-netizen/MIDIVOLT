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
