# MIDIVOLT Provider Completion Gate — offline verification

Date: 2026-11-01. Branch: `fix/midivolt-provider-completion-gate-20261101`.

## Executed evidence — PASS (limited)

Command run on an isolated Linux Python 3.13 environment:

```
python -m pytest -q /mnt/data/midivolt_provider_contract/tests/test_provider_contract_standalone.py
.......... [100%]
10 passed in 0.03s
```

Both copied test artifacts exactly match their GitHub **blob SHA**:

- `src/midivolt/_provider_contract.py`: `f688c2a7ac27c91b9d6548b2b6794561ee1c6500`
- `tests/test_provider_contract_standalone.py`: `07b3bdda2846789edb818bee8eee697d84aad046`

The tested dependency-free decoder is wired into the production
`src/midivolt/ai_midi.py` `_decode_response` entrypoint. Two additional
provider/CLI integration regressions were added in `tests/test_ai_midi.py`.

## Scope of ten tests

Completed OpenAI and Ollama reply accepted; missing OpenAI `finish_reason`,
truncation, refusal, missing/false Ollama `done`, blank text, malformed reply
and unknown provider rejected. No network or real model was called.

## NOT_RUN / unresolved

- Full `tests/test_ai_midi.py`, including the two newly added integration
  cases, was **not executed** in this slice.
- Actual HTTP to a real OpenAI/Ollama model: **NOT_RUN**.
- Real music model, generated MIDI musical quality, Python 3.11 Windows and
  Cubase round-trip: **NOT_RUN**.
- GitHub Actions: **NOT_USED**, because runner quota is unavailable.

This proves only the terminal-response protocol guard, not complete
AI-to-MIDI product acceptance. No code was merged to `main`.
