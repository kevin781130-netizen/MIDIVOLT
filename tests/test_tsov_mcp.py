"""MCP protocol and safety tests against a fake local stdio server."""

import sys

import pytest

from midivolt.tsov_cli import main
from midivolt.tsov_mcp import (
    McpStdioSession, TsovMcpError, tsov_command, validate_project,
)

FAKE_SERVER = r'''
import json,sys

for line in sys.stdin:
    msg = json.loads(line)
    if 'id' not in msg:
        continue
    method = msg['method']
    if method == 'initialize':
        result = {'protocolVersion':'2025-06-18','capabilities':{'tools':{}},
                  'serverInfo':{'name':'fake-tsov','version':'1'}}
    elif method == 'tools/list':
        result = {'tools':[{'name':n,'inputSchema':{'type':'object'}} for n in (
            'list_projects','project_status','list_history',
            'edit_score','undo','redo','set_tempo')]}
    elif method == 'tools/call':
        tool = msg['params']['name']
        args = msg['params']['arguments']
        if tool == 'edit_score' and args.get('feedback') == 'fail':
            result = {'isError':True,
                      'content':[{'type':'text','text':'no llm endpoint'}]}
        else:
            payload = json.dumps({'tool':tool, 'arguments':args,
                                  'diff':{'notes_added':2}})
            if tool == 'set_tempo':
                payload += '\n\nWebUI co-existence guard notice'
            result = {'isError':False,
                      'content':[{'type':'text','text':payload}]}
    else:
        result = {}
    print(json.dumps({'jsonrpc':'2.0','id':msg['id'],'result':result}),
          flush=True)
'''


def fake_cmd(tmp_path):
    server = tmp_path / "mcp_stub.py"
    server.write_text(FAKE_SERVER, encoding="utf-8")
    return [sys.executable, str(server)]


def test_real_json_rpc_session_lists_and_reads(tmp_path):
    with McpStdioSession(fake_cmd(tmp_path)) as client:
        assert "project_status" in client.available_tools
        assert client.call("project_status", {"project":"song"})[
            "arguments"]["project"] == "song"
        with pytest.raises(PermissionError):
            client.call("edit_score", {"project":"song","feedback":"change"})
        with pytest.raises(ValueError):
            client.call("dangerous_tool", {})


def test_explicit_write_and_server_error(tmp_path):
    with McpStdioSession(fake_cmd(tmp_path), allow_write=True) as client:
        result = client.call(
            "edit_score",
            {"project":"song","feedback":"add strings","track":1},
        )
        assert result["diff"]["notes_added"] == 2
        with pytest.raises(TsovMcpError, match="no llm endpoint"):
            client.call("edit_score", {"project":"song","feedback":"fail"})


def test_coexistence_notice_keeps_structured_diff(tmp_path):
    with McpStdioSession(fake_cmd(tmp_path), allow_write=True) as client:
        result = client.call("set_tempo", {"project":"song", "tempo":70})
        assert result["diff"]["notes_added"] == 2
        assert "co-existence" in result["bridge_notice"]


def test_project_validation():
    for s in ("", "..", "../secret", "project/name",
              "project\\\\name", "bad\\nline", " x "):
        with pytest.raises(ValueError):
            validate_project(s)
    assert validate_project("小提琴 01") == "小提琴 01"


def test_spawn_without_shell_or_autoinstall(tmp_path):
    root = tmp_path / "tsov checkout"
    (root / "tsov").mkdir(parents=True)
    (root / "tsov" / "cli.py").write_text("")
    argv = tsov_command(sys.executable, root, allow_write=False)
    assert argv[0] == sys.executable
    assert argv[1:4] == ["-m", "tsov.cli", "mcp"]
    assert "--allow-write" not in argv
    assert "--web-guard" in argv and "strict" in argv
    assert "--allow-write" in tsov_command(sys.executable, root,
                                            allow_write=True)


def test_closed_server_cleans_up(tmp_path):
    with pytest.raises(TsovMcpError):
        with McpStdioSession([sys.executable, "-c", "pass"], timeout=2):
            pass


def test_cli_requires_explicit_apply(tmp_path, capsys):
    ret = main([
        "--python", "missing.exe", "--root", str(tmp_path),
        "edit", "--project", "a", "--track", "0",
        "--feedback", "rewrite",
    ])
    assert ret == 2
    assert "--apply" in capsys.readouterr().err


def test_cli_rejects_bad_bpm_and_project(tmp_path):
    assert main([
        "--python","missing.exe","--root",str(tmp_path),
        "tempo","--project","a","--bpm","nan","--apply",
    ]) == 2
    assert main([
        "--python","missing.exe","--root",str(tmp_path),
        "status","--project","../unsafe",
    ]) == 2
