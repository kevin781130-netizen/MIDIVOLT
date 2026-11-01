# MIDIVOLT — Ollama terminal-reason fail-closed regression

Date: 2026-11-01
Branch: `fix/midivolt-ollama-terminal-reason-20261101`

## Reproduced issue

Previously `decode_response_text("ollama", ...)` accepted a response with
`done=true` and `done_reason="length"`, even if its JSON looked valid.
That does **not** establish that the model completed its requested musical
output. This was reproduced using the unchanged GitHub blob
`f688c2a7ac27c91b9d6548b2b6794561ee1c6500`.

## Fix and executed test result

Require an Ollama response to report `done=true` and, if
`done_reason` is provided, it must equal `stop`.
Absent `done_reason` is accepted for compatibility with existing responses;
other explicit reasons fail closed.

```
cd /mnt/data/midivolt_provider_contract
python -m pytest -q tests/test_provider_contract_standalone.py
............ [100%]
12 passed in 0.03s
```

Environment: isolated Linux, Python 3.13.5, pytest 9.0.2.
No GitHub Actions, real LLM, Cubase or network request involved.

Independently checked exact `git hash-object` values of the tested files:

- `src/midivolt/_provider_contract.py`:
  `312091068d2fa51d24c189e0be8b26e509f3a42f`
- `tests/test_provider_contract_standalone.py`:
  `06a77d249ad22c01a853b90ccea26bcf4c71faf5`

Both match this branch's GitHub blob SHA. The existing production
`src/midivolt/ai_midi.py` delegates to this decoder.

Added a full-pipeline regression
`test_ollama_done_true_but_length_stop_never_publishes_midi` to
`tests/test_ai_midi.py`; **that new integration test has not been executed**.

## Remaining gates

- `tests/test_ai_midi.py`: NOT_RUN in this slice. Repository checkout cannot
  be obtained through the isolated container's blocked GitHub network; source
  was inspected via the connected GitHub API.
- Supported Python 3.11, real OpenAI/Ollama inference, musical quality and
  Windows Cubase GUI: NOT_RUN.
- No changes to `main`; no GitHub Actions used.

Scope of this PASS: only 12 isolated completion-protocol regressions. It does
**not** certify the complete AI Provider -> MIDI -> review chain.
