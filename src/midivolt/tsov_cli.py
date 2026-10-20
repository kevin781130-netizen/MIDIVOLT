"""MIDIVOLT external tsov MCP CLI: read-only by default."""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

from .tsov_mcp import McpStdioSession, TsovMcpError, tsov_command, validate_project


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="midivolt-tsov",
        description="Call separately installed tsov MCP. Writes require --apply.",
    )
    p.add_argument("--python", required=True,
                   help="tsov Python 3.12 virtualenv executable")
    p.add_argument("--root", required=True,
                   help="Path to the separately cloned tsov repo")
    p.add_argument("--timeout", type=float, default=60.0)
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("projects", help="List tsov projects")
    sub.add_parser("tools", help="List permitted MCP tools offered by tsov")
    for name in ("status", "history", "undo", "redo"):
        c = sub.add_parser(name)
        c.add_argument("--project", required=True)
        if name == "history":
            c.add_argument("--limit", type=int, default=20)
        if name in ("undo", "redo"):
            c.add_argument("--apply", action="store_true")
    edit = sub.add_parser("edit", help="Apply LLM edit to one selected track")
    edit.add_argument("--project", required=True)
    edit.add_argument("--track", required=True,
                      help="Explicit track name or index")
    edit.add_argument("--feedback", required=True)
    edit.add_argument("--apply", action="store_true")
    tempo = sub.add_parser("tempo", help="Change project BPM")
    tempo.add_argument("--project", required=True)
    tempo.add_argument("--bpm", type=float, required=True)
    tempo.add_argument("--remap", action="store_true",
                       help="Also rescale time; default only changes BPM header")
    tempo.add_argument("--apply", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    writing = args.command in {"edit", "tempo", "undo", "redo"}
    try:
        if not math.isfinite(args.timeout) or args.timeout <= 0 or args.timeout > 600:
            raise ValueError("--timeout must be between 0 and 600 seconds.")
        if writing and not args.apply:
            raise PermissionError("Refusing project mutation without --apply.")
        if hasattr(args, "project"):
            validate_project(args.project)
        if args.command == "edit" and (
            not args.feedback.strip() or not args.track.strip()
        ):
            raise ValueError("--feedback and --track must not be empty.")
        if args.command == "tempo" and (
            not math.isfinite(args.bpm) or not 20 <= args.bpm <= 400
        ):
            raise ValueError("--bpm must be finite and between 20 and 400.")
        command = tsov_command(args.python, args.root, allow_write=writing)
        with McpStdioSession(
            command, cwd=Path(args.root).resolve(),
            timeout=args.timeout, allow_write=writing,
        ) as session:
            if args.command == "projects":
                result = session.call("list_projects")
            elif args.command == "tools":
                result = {"tools": list(session.available_tools)}
            elif args.command == "status":
                result = session.call("project_status",
                                      {"project": args.project})
            elif args.command == "history":
                if not 1 <= args.limit <= 100:
                    raise ValueError("--limit must be 1..100.")
                result = session.call(
                    "list_history", {"project": args.project, "limit": args.limit})
            elif args.command == "edit":
                track = int(args.track) if (
                    args.track.isascii() and args.track.isdecimal()
                ) else args.track
                result = session.call("edit_score", {
                    "project": args.project, "track": track,
                    "feedback": args.feedback,
                })
            elif args.command == "tempo":
                result = session.call("set_tempo", {
                    "project": args.project, "tempo": args.bpm,
                    "remap": args.remap,
                })
            else:
                result = session.call(
                    args.command, {"project": args.project})
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
    except (ValueError, PermissionError, FileNotFoundError,
            OSError, TsovMcpError) as exc:
        print(f"MIDIVOLT tsov MCP: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
