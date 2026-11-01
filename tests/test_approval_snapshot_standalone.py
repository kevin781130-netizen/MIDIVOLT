"""Dependency-free regression of approved MIDI source/candidate snapshots."""
from __future__ import annotations

import importlib.util
from hashlib import sha256
from pathlib import Path
import tempfile
import unittest

MODULE = Path(__file__).resolve().parents[1] / "src/midivolt/_approval_snapshot.py"
spec = importlib.util.spec_from_file_location("_approval_snapshot", MODULE)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


class ApprovalSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.source = root / "source.mid"
        self.candidate = root / "candidate.mid"
        self.source.write_bytes(b"MThd" + b"source")
        self.candidate.write_bytes(b"MThd" + b"candidate")
        self.source_sha = digest(self.source)
        self.candidate_sha = digest(self.candidate)

    def freeze(self):
        return mod.read_approved_snapshots(
            self.source, self.candidate, self.source_sha, self.candidate_sha)

    def test_exact_reviewed_bytes_returned(self):
        original, proposed = self.freeze()
        self.assertEqual(original, self.source.read_bytes())
        self.assertEqual(proposed, self.candidate.read_bytes())

    def test_source_changed_since_review_rejected(self):
        self.source.write_bytes(b"MThd" + b"different source")
        with self.assertRaisesRegex(ValueError, "Source MIDI changed"):
            self.freeze()

    def test_candidate_changed_since_review_rejected(self):
        self.candidate.write_bytes(b"MThd" + b"different candidate")
        with self.assertRaisesRegex(ValueError, "Candidate MIDI changed"):
            self.freeze()

    def test_frozen_bytes_not_affected_by_subsequent_replacement(self):
        original, proposed = self.freeze()
        self.source.write_bytes(b"changed after freeze")
        self.candidate.write_bytes(b"changed after freeze")
        self.assertEqual(original, b"MThdsource")
        self.assertEqual(proposed, b"MThdcandidate")

    def test_invalid_or_missing_hash_refused(self):
        with self.assertRaisesRegex(ValueError, "Invalid approved source"):
            mod.read_approved_snapshots(self.source, self.candidate, "not-a-hash", self.candidate_sha)

    def test_deleted_candidate_refused(self):
        self.candidate.unlink()
        with self.assertRaises(FileNotFoundError):
            self.freeze()


if __name__ == "__main__":
    unittest.main()
