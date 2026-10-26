# Cut31 — OpenAI / Ollama provider to editable multitrack MIDI

Status: **real provider request adapters implemented; trained provider inference not yet acceptance-tested**.
Focus: independent MIDI Agent-style capability without copying its source, design or weights.

## Implemented

- src/midivolt/ai_midi.py: JSON-only OpenAI Chat Completions and Ollama native chat requests.
- src/midivolt/ai_cli.py: midivolt-ai command with network consent and source protection.
- Tests exercise provider response decoding, note validation, source preservation, local real TCP HTTP service and the existing review/apply gate.
- No auto-generated API keys, hidden checkpoint installs or silent fallback to deterministic music.

## Try OpenAI API from your own machine

Create an OpenAI API key in the developer dashboard; ChatGPT subscriptions alone do not grant API use. Store the secret in the environment and do not commit or print it.

```powershell
$env:MIDIVOLT_OPENAI_API_KEY = 'YOUR_SECRET_API_KEY'
midivolt-ai --provider openai --model YOUR_SUPPORTED_MODEL --prompt '8 bars of chord, melody, bass and drums in D minor, 110 bpm' --out generated.mid --allow-network
```

Default TLS API endpoint: https://api.openai.com/v1/chat/completions. Uses response_format json_object plus local semantic validation. Actual inference depends on a supported account/model, network and provider billing.

## Try local Ollama

Install and start Ollama separately and provide an already installed model:

```powershell
midivolt-ai --provider ollama --model YOUR_LOCAL_MODEL --prompt '4 bars of bass and melody in A minor, 100 bpm' --out local.mid --allow-network
```

Default local endpoint: http://127.0.0.1:11434/api/chat, JSON format, stream=false. Local inference quality is model-dependent. All calls require --allow-network even for loopback.

## Continue existing MIDI, do not overwrite original

```powershell
midivolt-ai --provider ollama --model YOUR_LOCAL_MODEL --input intro.mid --manifest proposal.json --prompt 'Extend with 4 bars of melody and bass' --out candidate.mid --allow-network
midivolt-review preview --manifest proposal.json
midivolt-review apply --manifest proposal.json --out approved.mid --approve
```

All source MIDI tracks are locked by default. Existing source MIDI content is sent as a bounded JSON context to the selected service; do not share confidential source music with external APIs without permission.

## Data contract

```json
{"tracks":[{"role":"melody","notes":[{"pitch":62,"start_beat":0,"duration_beats":1,"velocity":90}]}]}
```

Role must match requested parts and each track contain 1..1024 events. Pitches 0..127, GM drum pitches 35..81, velocity 1..127; all finite beat coordinates must fall within requested 1..32 new 4/4 bars. Untrusted extra fields, malformed JSON, empty note lists, duplicated roles, missing roles, overflowed notes and provider refusals stop without publishing a MIDI file. Existing source tempo must be constant and meter 4/4.

## Credential/network safety

- OpenAI credential sourced from environment variable MIDIVOLT_OPENAI_API_KEY by default; never stored in a MIDI or report.
- Cloud calls must use HTTPS. Custom remote endpoints require --allow-remote-endpoint, plus --allow-network. Remote plaintext HTTP is refused.
- HTTP redirects are disabled; maximum request/response 256k bytes; context is limited to 160 source notes and timeout to 120 seconds.
- Reports contain only provider/model labels, validity booleans and SHA-256 prompt/response fingerprints; no API key or raw private model response.

## What was and was not tested

Tests using a fake local Ollama HTTP server confirm actual network I/O and serialized MIDI can work, but that service is deliberately not a trained AI model. Real OpenAI API charges, trained model response quality, Claude/Gemini, iterative chat, Windows standalone and VST3/AU/AAX are not verified. No commercial Beta promotion follows merely from passing this test.

References: https://platform.openai.com/docs/api-reference/chat/create and https://www.midiagent.com/features
