# MIDIVOLT: external tsov MCP agent (experimental)

**Integration mode:** standard MCP JSON-RPC through a separate tsov process. MIDIVOLT does not copy, link, vendor, relicense or bundle tsov code, data or checkpoints.

## Separate environments

MIDIVOLT uses Python 3.11. tsov requires its own Python 3.12 environment and an independent checkout: https://github.com/luolianst/tsov. Follow tsov setup instructions and install its MCP SDK (upstream source requests mcp==2.3.0). No tsov dependency is installed by MIDIVOLT.

With MIDIVOLT installed, supply tsov's actual Python 3.12 executable and repo location:

    midivolt-tsov --python "C:\\tsov\\.venv\\Scripts\\python.exe" --root "C:\\tsov" projects
    midivolt-tsov --python "C:\\tsov\\.venv\\Scripts\\python.exe" --root "C:\\tsov" tools
    midivolt-tsov --python "C:\\tsov\\.venv\\Scripts\\python.exe" --root "C:\\tsov" status --project demo
    midivolt-tsov --python "C:\\tsov\\.venv\\Scripts\\python.exe" --root "C:\\tsov" history --project demo

tsov projects live at tsov/output/<project>/score.json. Create a tsov project first by importing the MIDI produced by the separate midivolt-bridge command into tsov WebUI.

## Write approval and diff/undo

The following **change** tsov files; the required --apply is deliberately explicit. Use tsov's own diff returned by edit_score and undo to review/revert results.

    midivolt-tsov --python "C:\\tsov\\.venv\\Scripts\\python.exe" --root "C:\\tsov" edit --project demo --track 0 --feedback "Preserve the motif and add a gentle variation" --apply
    midivolt-tsov --python "C:\\tsov\\.venv\\Scripts\\python.exe" --root "C:\\tsov" undo --project demo --apply
    midivolt-tsov --python "C:\\tsov\\.venv\\Scripts\\python.exe" --root "C:\\tsov" redo --project demo --apply
    midivolt-tsov --python "C:\\tsov\\.venv\\Scripts\\python.exe" --root "C:\\tsov" tempo --project demo --bpm 70 --apply

No generic agent loop is built into MIDIVOLT yet: edit calls tsov's actual edit_score MCP tool, which in turn uses tsov's configured LLM endpoint. Edits are **applied before** the diff is returned, not previewed for pre-approval. --track is always required for edits.

## Safety and known limitations

- Separate subprocess executes: python -m tsov.cli mcp --root ROOT --web-guard strict.
- Read-only commands do not pass --allow-write; write commands require --apply then launch tsov with --allow-write.
- Client permits only list_projects, project_status, list_history, edit_score, set_tempo, undo, redo, and only when actually advertised by tsov.
- No remote server, arbitrary MCP tools, shell execution, hidden model downloads or credential copying.
- MCP responses have a 4 MiB limit and per-request timeout (default 60 s; --timeout up to 600). Stopped child processes are cleaned up.
- Windows, original tsov MCP server, GPU/model performance, LLM endpoint and audio quality are **not** covered by mocked local tests.
- Unit tests: pytest -q tests/test_tsov_mcp.py. These test a fake stdio MCP server and the client guardrails, not a real tsov integration run.

## License boundary

MIDIVOLT: Apache-2.0. tsov: AGPL-3.0. Separately installing and invoking tsov by stdio is a design choice, **not a legal guarantee**. Bundling both programs, modifying tsov or hosting a modified network service may carry AGPL source-distribution obligations. Review the final commercial distribution with qualified counsel.
