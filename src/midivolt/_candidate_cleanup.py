"""Dependency-free, conservative cleanup for unpublished AI MIDI candidates.

Cleanup is best-effort, not a transactional multi-file commit. When another
process may own the destination, preserve it rather than risking data loss.
"""
from __future__ import annotations

from hashlib import file_digest
from pathlib import Path
from stat import S_ISREG

CandidateIdentity = tuple[int, int, int, str]


def _sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return file_digest(stream, "sha256").hexdigest()


def capture_published_candidate(path: Path) -> CandidateIdentity:
    """Capture identity and bytes of a regular published file (not a symlink)."""
    path = Path(path)
    before = path.lstat()
    if not S_ISREG(before.st_mode):
        raise ValueError("Candidate is not a regular file")
    digest = _sha256(path)
    after = path.lstat()
    attributes = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
    if attributes(before) != attributes(after) or not S_ISREG(after.st_mode):
        raise ValueError("Candidate changed while recording its identity")
    return before.st_dev, before.st_ino, before.st_size, digest


def discard_candidate_if_unchanged(path: Path, expected: CandidateIdentity) -> bool:
    """Best-effort rollback only when the same regular file retains its bytes.

    Not a cross-process atomic operation: edits between the final check and
    unlink are still possible. Caller must not claim unconditional isolation.
    """
    path = Path(path)
    try:
        before = path.lstat()
        if not S_ISREG(before.st_mode):
            return False
        if (before.st_dev, before.st_ino, before.st_size) != expected[:3]:
            return False
        if capture_published_candidate(path) != expected:
            return False
        after = path.lstat()
        if not S_ISREG(after.st_mode) or (after.st_dev, after.st_ino, after.st_size) != expected[:3]:
            return False
        path.unlink()
        return True
    except (OSError, ValueError):
        return False
