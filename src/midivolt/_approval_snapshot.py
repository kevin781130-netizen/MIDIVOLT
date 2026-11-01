"""Freeze and verify approved MIDI bytes before publishing a new file.

No network, model, DAW, or third-party dependency. The two returned byte
strings are the ONLY versions that may be used for final MIDI serialization.
"""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path


def read_approved_snapshots(source: Path, candidate: Path,
                            expected_source_sha256: str,
                            expected_candidate_sha256: str) -> tuple[bytes, bytes]:
    """Refuse changed files and freeze exactly the manifest-approved bytes.

    Does not lock other processes out of the source or candidate files; users
    must not infer filesystem-wide transactional guarantees from this gate.
    """
    result = []
    for label, filename, expected in (
        ("Source", Path(source), expected_source_sha256),
        ("Candidate", Path(candidate), expected_candidate_sha256),
    ):
        if not isinstance(expected, str) or len(expected) != 64 or any(
                ch not in "0123456789abcdef" for ch in expected):
            raise ValueError(f"Invalid approved {label.lower()} SHA-256")
        payload = filename.read_bytes()
        if sha256(payload).hexdigest() != expected:
            raise ValueError(f"{label} MIDI changed during approval; output not published")
        result.append(payload)
    return result[0], result[1]
