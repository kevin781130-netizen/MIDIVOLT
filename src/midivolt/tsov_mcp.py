"""Safely operate an independently installed tsov MCP server over stdio.

This original, dependency-free client does not copy AGPL tsov source.
The server runs in a separate Python 3.12 environment and project root.
"""
from __future__ import annotations

import json
import queue
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

PROTOCOL_VERSION = "2025-06-18"
MAX_MESSAGE_BYTES = 4 * 1024 * 1024
READ_TOOLS = frozenset({"list_projects", "project_status", "list_history"})
WRITE_TOOLS = frozenset({"edit_score", "set_tempo", "undo", "redo"})
ALLOWED_TOOLS = READ_TOOLS | WRITE_TOOLS


class TsovMcpError(RuntimeError):
    """MCP transport, server, or permission failure."""


def validate_project(name: str) -> str:
    if not isinstance(name, str) or not name or name.strip() != name:
        raise ValueError("Provide a nonempty tsov project name without leading/trailing spaces.")
    if name in {".", ".."} or len(name) > 160 or any(c in name for c in "/\\\r\n\0"):
        raise ValueError("Invalid tsov project name.")
    return name


def tsov_command(python_executable: str | Path, root: str | Path, *, allow_write: bool) -> list[str]:
    """Construct explicit argv, without a shell or automatic installer."""
    location = Path(root).expanduser().resolve(strict=True)
    if not location.is_dir() or not (location / "tsov" / "cli.py").is_file():
        raise ValueError("--root must be a tsov repository with tsov/cli.py.")
    binary = Path(python_executable).expanduser()
    if not binary.is_file():
        raise FileNotFoundError(f"tsov Python executable not found: {binary}")
    cmd = [str(binary.resolve()), "-m", "tsov.cli", "mcp",
           "--root", str(location), "--web-guard", "strict"]
    if allow_write:
        cmd.append("--allow-write")
    return cmd


class McpStdioSession:
    """Bounded MCP JSON-RPC stdio session, with child cleanup and timeouts."""

    def __init__(self, argv: list[str], *, cwd: Path | None = None,
                 timeout: float = 30.0, allow_write: bool = False):
        if not argv or timeout <= 0:
            raise ValueError("Nonempty command and positive timeout required.")
        self.argv, self.cwd, self.timeout = list(argv), cwd, timeout
        self.allow_write = bool(allow_write)
        self._proc: subprocess.Popen[bytes] | None = None
        self._messages: queue.Queue[bytes | Exception | None] = queue.Queue()
        self._next_id = 0
        self._tools: frozenset[str] = frozenset()

    def __enter__(self) -> McpStdioSession:
        try:
            self._proc = subprocess.Popen(
                self.argv, cwd=str(self.cwd) if self.cwd else None,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, shell=False,
            )
            threading.Thread(
                target=self._read_stdout, args=(self._proc,),
                name="midivolt-mcp-reader", daemon=True,
            ).start()
            handshake = self._request(
                "initialize", {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": {"name": "MIDIVOLT", "version": "0.1.0"},
                },
            )
            if not isinstance(handshake, dict) or not handshake.get("protocolVersion"):
                raise TsovMcpError("Invalid MCP initialize response.")
            self._notify("notifications/initialized")
            offered = self._request("tools/list", {})
            if not isinstance(offered, dict) or not isinstance(offered.get("tools"), list):
                raise TsovMcpError("Invalid MCP tools/list response.")
            self._tools = frozenset(
                t["name"] for t in offered["tools"]
                if isinstance(t, dict) and isinstance(t.get("name"), str)
            )
            return self
        except BaseException:
            self.close()
            raise

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    @property
    def available_tools(self) -> tuple[str, ...]:
        return tuple(sorted(self._tools & ALLOWED_TOOLS))

    def close(self) -> None:
        proc = self._proc
        self._proc = None
        if proc is None:
            return
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=2.0)
        for stream in (proc.stdin, proc.stdout):
            if stream:
                stream.close()

    def _read_stdout(self, proc: subprocess.Popen[bytes]) -> None:
        assert proc.stdout is not None
        try:
            while True:
                line = proc.stdout.readline(MAX_MESSAGE_BYTES + 1)
                if not line:
                    break
                if len(line) > MAX_MESSAGE_BYTES:
                    self._messages.put(TsovMcpError("MCP response exceeds 4 MiB limit."))
                    break
                self._messages.put(line)
        except (OSError, ValueError) as exc:
            self._messages.put(exc)
        finally:
            self._messages.put(None)

    def _send(self, payload: dict[str, Any]) -> None:
        proc = self._proc
        if proc is None or proc.stdin is None or proc.poll() is not None:
            raise TsovMcpError(
                "tsov MCP process is not running. Check Python and mcp SDK.")
        raw = (json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
        try:
            proc.stdin.write(raw)
            proc.stdin.flush()
        except (OSError, BrokenPipeError) as exc:
            raise TsovMcpError("tsov MCP process closed stdin.") from exc

    def _notify(self, method: str) -> None:
        self._send({"jsonrpc": "2.0", "method": method})

    def _request(self, method: str, params: dict[str, Any]) -> Any:
        self._next_id += 1
        request_id = self._next_id
        self._send({"jsonrpc": "2.0", "id": request_id,
                    "method": method, "params": params})
        deadline = time.monotonic() + self.timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TsovMcpError(
                    f"Timed out waiting for tsov MCP {method} ({self.timeout:g}s).")
            try:
                item = self._messages.get(timeout=remaining)
            except queue.Empty as exc:
                raise TsovMcpError(
                    f"Timed out waiting for tsov MCP {method} ({self.timeout:g}s).") from exc
            if item is None:
                raise TsovMcpError(
                    "tsov MCP closed stdout unexpectedly. "
                    "Verify mcp==2.3.0 in its Python 3.12 venv.")
            if isinstance(item, Exception):
                raise TsovMcpError(str(item)) from item
            try:
                msg = json.loads(item.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise TsovMcpError("Invalid JSON on tsov MCP stdout.") from exc
            if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0":
                raise TsovMcpError("Invalid MCP JSON-RPC envelope.")
            if "id" not in msg:
                continue
            if msg["id"] != request_id:
                raise TsovMcpError("Unexpected MCP request ID.")
            if "error" in msg:
                error = msg["error"]
                detail = error.get("message", "unknown") if isinstance(error, dict) else str(error)
                raise TsovMcpError(f"tsov MCP {method} error: {detail}")
            if "result" not in msg:
                raise TsovMcpError("MCP response missing result.")
            return msg["result"]

    def call(self, tool: str, arguments: dict[str, Any] | None = None) -> Any:
        if tool not in ALLOWED_TOOLS:
            raise ValueError(f"MIDIVOLT does not permit MCP tool {tool!r}.")
        if tool in WRITE_TOOLS and not self.allow_write:
            raise PermissionError(
                "tsov writes are disabled. Explicitly authorize a write action.")
        if tool not in self._tools:
            raise TsovMcpError(
                f"tsov MCP server did not advertise {tool!r} "
                "(check --allow-write/version).")
        values = dict(arguments or {})
        if "project" in values:
            values["project"] = validate_project(values["project"])
        result = self._request(
            "tools/call", {"name": tool, "arguments": values})
        if not isinstance(result, dict) or not isinstance(result.get("content"), list):
            raise TsovMcpError("Invalid tools/call payload.")
        texts = [
            block["text"] for block in result["content"]
            if isinstance(block, dict) and block.get("type") == "text"
            and isinstance(block.get("text"), str)
        ]
        merged = "\n".join(texts)
        if result.get("isError") or result.get("is_error"):
            raise TsovMcpError(
                f"tsov {tool} rejected request: {merged[:1000]}")
        try:
            return json.loads(merged)
        except json.JSONDecodeError:
            head, separator, notice = merged.partition("\n")
            try:
                decoded = json.loads(head)
            except json.JSONDecodeError:
                return {"text": merged}
            if separator and notice.strip():
                if isinstance(decoded, dict):
                    return {**decoded, "bridge_notice": notice.strip()}
                return {"result": decoded, "bridge_notice": notice.strip()}
            return decoded
