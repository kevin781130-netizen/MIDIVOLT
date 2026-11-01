"""Standalone candidate-publishing safety tests: stdlib only, no model or DAW."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import tempfile
import unittest

MODULE = Path(__file__).resolve().parents[1] / "src/midivolt/_candidate_cleanup.py"
spec = importlib.util.spec_from_file_location("candidate_cleanup", MODULE)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class CandidateCleanupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.target = Path(self.tmp.name) / "candidate.mid"
        self.target.write_bytes(b"MThd" + b"A" * 64)

    def test_unchanged_candidate_is_rolled_back(self):
        identity = mod.capture_published_candidate(self.target)
        self.assertTrue(mod.discard_candidate_if_unchanged(self.target, identity))
        self.assertFalse(self.target.exists())

    def test_modified_candidate_is_preserved(self):
        identity = mod.capture_published_candidate(self.target)
        self.target.write_bytes(b"MThd" + b"B" * 64)
        self.assertFalse(mod.discard_candidate_if_unchanged(self.target, identity))
        self.assertTrue(self.target.exists())

    def test_replaced_candidate_is_preserved(self):
        identity = mod.capture_published_candidate(self.target)
        replacement = Path(self.tmp.name) / "replacement.mid"
        replacement.write_bytes(b"MThd" + b"C" * 64)
        os.replace(replacement, self.target)
        self.assertFalse(mod.discard_candidate_if_unchanged(self.target, identity))
        self.assertEqual(self.target.read_bytes(), b"MThd" + b"C" * 64)

    def test_missing_candidate_is_safe(self):
        identity = mod.capture_published_candidate(self.target)
        self.target.unlink()
        self.assertFalse(mod.discard_candidate_if_unchanged(self.target, identity))

    def test_symlink_candidate_is_preserved(self):
        identity = mod.capture_published_candidate(self.target)
        other = Path(self.tmp.name) / "other.mid"
        other.write_bytes(b"MThd" + b"D" * 64)
        self.target.unlink()
        try:
            self.target.symlink_to(other)
        except (OSError, NotImplementedError):
            self.skipTest("platform forbids symlinks")
        self.assertFalse(mod.discard_candidate_if_unchanged(self.target, identity))
        self.assertTrue(self.target.is_symlink())
        self.assertTrue(other.exists())


if __name__ == "__main__":
    unittest.main()
