"""Opt-in release-gate smoke of actual, pinned Text2midi composition weights."""

from __future__ import annotations

import argparse
import json
import sys

from .composition_acceptance import run_composition_acceptance
from .environments import EnvironmentError
from .part_orchestrator import parse_program_assignments


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="midivolt-compose-accept",
        description="Run trusted local pretrained Text2midi across the FULL strict-parts path; no dummy model.",
    )
    for flag in ("env", "checkout", "checkpoint", "checkpoint-sha256",
                 "vocab", "vocab-sha256", "t5-dir", "source",
                 "candidate", "manifest", "report", "prompt"):
        p.add_argument("--" + flag, required=True)
    p.add_argument("--lock", type=int, action="append", required=True)
    p.add_argument("--program", action="append", metavar="ROLE=GM")
    p.add_argument("--confirm-inference", action="store_true")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--timeout", type=float, default=1800.0)
    p.add_argument("--temperature", type=float, default=0.9)
    p.add_argument("--max-tokens", type=int, default=2000)
    p.add_argument("--max-new-tracks", type=int, default=16)
    p.add_argument("--max-new-notes", type=int, default=20000)
    p.add_argument("--retry-per-part", type=int, default=1)
    p.add_argument("--min-structure-score", type=float, default=0.75)
    p.add_argument("--harmonic-key")
    p.add_argument("--harmonic-chords")
    p.add_argument("--beats-per-chord", type=float, default=4.0)
    p.add_argument("--min-harmony-score", type=float)
    return p


def main(argv: list[str] | None = None) -> int:
    a = build_parser().parse_args(argv)
    try:
        result = run_composition_acceptance(
            confirm_inference=a.confirm_inference, environment=a.env,
            checkout=a.checkout, checkpoint=a.checkpoint,
            checkpoint_sha256=a.checkpoint_sha256, vocab=a.vocab,
            vocab_sha256=a.vocab_sha256, t5_dir=a.t5_dir,
            source=a.source, candidate=a.candidate,
            manifest=a.manifest, report=a.report,
            prompt=a.prompt, locked_tracks=a.lock,
            program_assignments=parse_program_assignments(a.program),
            seed=a.seed, timeout=a.timeout, temperature=a.temperature,
            max_tokens=a.max_tokens, max_new_tracks=a.max_new_tracks,
            max_total_notes=a.max_new_notes, quality_retries=a.retry_per_part,
            minimum_structure_score=a.min_structure_score,
            harmonic_key=a.harmonic_key, harmonic_chords=a.harmonic_chords,
            beats_per_chord=a.beats_per_chord,
            minimum_harmony_score=a.min_harmony_score,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, PermissionError, TypeError, RuntimeError,
            EnvironmentError, KeyError, IndexError) as exc:
        print(f"MIDIVOLT real composition acceptance error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
