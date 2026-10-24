"""Review-first AI composition CLI for an explicitly provisioned local Text2midi."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .composition_engine import CompositionRequest, compose_candidate
from .io import read_midi, write_midi
from .local_model_provider import LocalText2MidiProvider
from .part_orchestrator import compose_strict_parts, parse_program_assignments
from .review_engine import create_proposal


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="midivolt-compose")
    parser.add_argument("--source", required=True, help="Original MIDI; never modified")
    parser.add_argument("--prompt", required=True, help="Musical instructions for local Text2midi")
    parser.add_argument("--python", required=True, help="Separate model-environment Python")
    parser.add_argument("--checkout", required=True, help="Trusted upstream model source")
    parser.add_argument("--checkpoint", required=True, help="Trusted local model checkpoint")
    parser.add_argument("--vocab", required=True, help="Trusted local REMI pickle vocabulary")
    parser.add_argument("--t5-dir", required=True, help="Local T5 tokenizer files")
    parser.add_argument("--candidate", required=True, help="NEW proposed multitrack MIDI")
    parser.add_argument("--manifest", required=True, help="NEW review manifest JSON")
    parser.add_argument("--lock", type=int, action="append", required=True,
                        help="Original track index to preserve; repeat as needed")
    parser.add_argument("--strict-parts", action="store_true",
                        help="Generate and validate exactly one track per explicitly requested instrument")
    parser.add_argument("--program", action="append", metavar="ROLE=GM",
                        help="Required GM selection for ambiguous roles in --strict-parts mode")
    parser.add_argument("--seed", type=int)
    parser.add_argument("--timeout", type=float, default=1200.0)
    parser.add_argument("--temperature", type=float, default=0.9)
    parser.add_argument("--max-tokens", type=int, default=2000)
    parser.add_argument("--max-new-tracks", type=int, default=16)
    parser.add_argument("--max-new-notes", type=int, default=20000)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        source = Path(args.source).expanduser().resolve()
        candidate = Path(args.candidate).expanduser().resolve()
        manifest = Path(args.manifest).expanduser().resolve()
        if len({source, candidate, manifest}) != 3:
            raise ValueError("Source, candidate and manifest must be separate paths.")
        if candidate.suffix.lower() not in (".mid", ".midi"):
            raise ValueError("Candidate must be a .mid or .midi file.")
        if manifest.suffix.lower() != ".json":
            raise ValueError("Manifest must have a .json extension.")
        if not candidate.parent.is_dir() or not manifest.parent.is_dir():
            raise FileNotFoundError("Output parent directories must already exist.")
        if candidate.exists() or manifest.exists():
            raise FileExistsError("Candidate and manifest must both be new files.")
        source_midi = read_midi(source)
        provider = LocalText2MidiProvider(
            python_executable=args.python,
            checkout=args.checkout,
            checkpoint=args.checkpoint,
            vocab_path=args.vocab,
            t5_dir=args.t5_dir,
            timeout=args.timeout,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
        )
        plan = None
        if args.strict_parts:
            assignments = parse_program_assignments(args.program)
            generated, plan, _ = compose_strict_parts(
                source_midi, args.prompt, provider,
                locked_tracks=tuple(args.lock),
                program_assignments=assignments,
                seed=args.seed,
                max_new_tracks=args.max_new_tracks,
                max_total_notes=args.max_new_notes,
            )
        else:
            if args.program:
                raise ValueError("--program requires --strict-parts.")
            request = CompositionRequest(
                prompt=args.prompt,
                locked_tracks=tuple(args.lock),
                seed=args.seed,
                max_new_tracks=args.max_new_tracks,
                max_new_notes=args.max_new_notes,
            )
            generated, _ = compose_candidate(source_midi, provider, request)
        write_midi(generated, candidate)
        # Manifest binds the source and candidate hashes. Approval stays a
        # separate, explicit midivolt-review apply --approve operation.
        proposal = create_proposal(source, candidate, manifest, locked_tracks=args.lock)
        print(json.dumps({
            "provider": provider.name,
            "strict_parts": bool(args.strict_parts),
            "composition_plan": plan,
            "candidate": str(candidate),
            "manifest": str(manifest),
            "review": proposal["review"],
            "approved": False,
        }, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, TypeError, OSError, RuntimeError, KeyError, IndexError) as exc:
        print(f"MIDIVOLT compose error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
