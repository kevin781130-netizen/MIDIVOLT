"""MIDIVOLT opt-in provider API -> independently editable MIDI.

This is genuine network-capable AI inference when --allow-network is used
with a real provider/model. There are no user credentials bundled;
offline tests use a fake response/loopback server, not an AI checkpoint.
Existing MIDI is never modified, and AI proposals need explicit review.
"""
from __future__ import annotations

import argparse
from hashlib import file_digest
import json
from pathlib import Path
import sys

from .ai_midi import (
    AIProviderError, request_notes, generated_to_midi, inference_report,
)
from .io import read_midi, write_midi
from .prompt_music import parse_prompt
from .review_engine import create_proposal, inspect_arrangement


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="midivolt-ai", description=__doc__)
    p.add_argument("--provider", choices=["openai", "ollama"], required=True)
    p.add_argument("--model", required=True, help="Provider model ID or locally installed Ollama tag")
    p.add_argument("--prompt", required=True)
    p.add_argument("--out", type=Path, required=True,
                   help="NEW .mid file, source MIDI never overwritten")
    p.add_argument("--input", type=Path, help="Existing MIDI for safe continuation")
    p.add_argument("--manifest", type=Path,
                   help="Review manifest required when --input is used")
    p.add_argument("--lock", type=int, action="append",
                   help="Explicit source track lock; default locks ALL source tracks")
    p.add_argument("--parts", choices=["chords", "melody", "bass", "drums"],
                   nargs="+")
    p.add_argument("--bars", type=int)
    p.add_argument("--bpm", type=float)
    p.add_argument("--key")
    p.add_argument("--mode", choices=["minor", "major"])
    p.add_argument("--seed", type=int)
    p.add_argument("--endpoint", help="Optional explicit HTTPS/loopback API endpoint")
    p.add_argument("--allow-remote-endpoint", action="store_true",
                   help="Authorize sending prompts/key to non-default remote HTTPS endpoint")
    p.add_argument("--api-key-env", default="MIDIVOLT_OPENAI_API_KEY",
                   help="ENVIRONMENT VARIABLE NAME; never put key itself on command line")
    p.add_argument("--allow-network", action="store_true",
                   help="EXPLICIT consent to call selected AI provider")
    p.add_argument("--timeout", type=float, default=35.0)
    return p


def _source_digest(path: Path) -> str:
    """Hash the real input bytes without reading unbounded MIDI into memory."""
    with path.open("rb") as stream:
        return file_digest(stream, "sha256").hexdigest()


def execute(args: argparse.Namespace, *, transport=None) -> dict:
    # Validate ALL deterministic constraints and destination filenames
    # BEFORE billable network inference.
    input_file = args.input.resolve() if args.input else None
    target = args.out.resolve()
    manifest = args.manifest.resolve() if args.manifest else None
    if target.suffix.lower() not in (".mid", ".midi") or not target.parent.is_dir():
        raise ValueError("Output must be .mid/.midi in an existing folder")
    if target.exists():
        raise FileExistsError("MIDI output already exists; overwriting is forbidden")
    if input_file and not manifest:
        raise ValueError("Existing-MIDI AI extension requires --manifest and review")
    if not input_file and manifest:
        raise ValueError("--manifest is only used for an existing MIDI extension")
    if not input_file and args.lock is not None:
        raise ValueError("--lock requires existing --input MIDI")
    if manifest:
        if manifest.suffix.lower() != ".json" or not manifest.parent.is_dir():
            raise ValueError("Review manifest must be .json in an existing directory")
        if manifest.exists():
            raise FileExistsError("Review manifest already exists")
    paths = [p for p in (input_file, target, manifest) if p]
    if len(set(paths)) != len(paths):
        raise ValueError("Source, generated MIDI and review manifest paths must differ")
    source_digest = _source_digest(input_file) if input_file else None
    source = read_midi(input_file) if input_file else None
    if input_file and _source_digest(input_file) != source_digest:
        raise ValueError("Source MIDI changed while it was being read; AI inference cancelled")
    if input_file:
        locked = args.lock if args.lock is not None else list(range(len(source.instruments)))
        if not locked:
            raise ValueError("AI extension must lock at least one original MIDI track")
        if len(locked) != len(set(locked)) or any(
            type(n) is not int or not 0 <= n < len(source.instruments) for n in locked
        ):
            raise ValueError("Invalid or duplicated source track lock")
    else:
        locked = []
    bpm = args.bpm
    if source is not None and bpm is None:
        _, tempo = source.get_tempo_changes()
        if len(tempo) != 1:
            raise ValueError("AI extension currently requires constant MIDI tempo")
        bpm = float(tempo[0])
    spec = parse_prompt(
        args.prompt, key=args.key, mode=args.mode, bars=args.bars,
        bpm=bpm, parts=tuple(args.parts) if args.parts else None, seed=args.seed,
    )
    document = request_notes(
        provider=args.provider, model=args.model, spec=spec, source=source,
        endpoint=args.endpoint, api_key_env=args.api_key_env,
        allow_network=args.allow_network,
        allow_remote_endpoint=args.allow_remote_endpoint,
        timeout=args.timeout, transport=transport,
    )
    generated = generated_to_midi(document, spec, source=source)
    # A provider call can last minutes. Never publish an extension against a
    # source whose on-disk bytes changed since we constructed the AI context.
    if input_file and _source_digest(input_file) != source_digest:
        raise ValueError("Source MIDI changed during AI inference; candidate not published")
    if source is not None:
        # Reject any spurious modification before persisting a candidate.
        preview = inspect_arrangement(source, generated, locked)
        if preview["notes_removed"] != 0 or preview["notes_added"] <= 0:
            raise ValueError("AI must add new MIDI notes without removing original")
    write_midi(generated, target)
    response = inference_report(
        provider=args.provider, model=args.model, spec=spec,
        source=source, generated=generated, raw_document=document,
    )
    response["candidate_midi"] = str(target)
    if input_file:
        proposal = create_proposal(
            input_file, target, manifest, locked_tracks=locked,
        )
        response.update({
            "review_manifest": str(manifest),
            "locked_source_tracks": locked,
            "review_diff": proposal["review"],
            "approval_required": True,
            "source_modified": False,
        })
    else:
        response.update({
            "review_manifest": None, "approval_required": False,
            "source_modified": False,
        })
    return response


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        result = execute(args)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (AIProviderError, OSError, RuntimeError, ValueError, PermissionError) as exc:
        print(f"MIDIVOLT AI inference error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
