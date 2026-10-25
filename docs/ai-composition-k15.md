# K15 — Authentic Text2midi checkpoint load smoke, before MIDI generation

## What changed

The official Text2midi quickstart loads its REMI tokenizer (a Python pickle),
constructs the Transformer, resolves the FLAN-T5 base encoder, strictly loads
its checkpoint state dictionary, then loads the T5 tokenizer and runs
autoregressive decoding. K12 checks only *file presence, basic pinned model
source shape, installed package imports and optional CUDA compute*; it
cannot establish that the full model checkpoint actually matches the
Transformer or that the T5/REMI assets deserialize successfully.

K15 adds a **separate explicit checkpoint loading stage** to the existing
midivolt-compose-doctor command. It launches the **real K8 Text2midi runner**
with --load-only under the approved managed model interpreter, with offline
environment flags, Python -I isolated mode and a bounded timeout.

The actual runner:
- Imports the operator-approved upstream Transformer (potentially executable
  and untrusted third-party code) and local PyTorch/Transformers packages.
- Deserializes the operator-provided REMI .pkl file (**pickle can execute code**).
- Initializes its FLAN-T5 encoder using the *operator's local model
  directory only* (K12's exact-name guarded redirect).
- Loads the operator-provided checkpoint with torch.load(weights_only=True)
  and requires model.load_state_dict(state, strict=True): wrong tensor keys
  or incompatible architecture fail without silent fallback.
- Loads the local T5 tokenizer and confirms that the checkpoint and model
  have a positive parameter count.
- Emits an explicit load-only JSON with device, PyTorch version, vocabulary
  size, parameter count, load wall time and conservative evidence flags.

**There is no model.generate() call, MIDI decoder call, or MIDI output** in
K15's load-only stage. It does not prove the generator runs to completion,
that parts are acoustically correct, or that the checkpoint's training data
have clear commercial rights.

## Model workstation procedure (Windows PowerShell)

Install the MIDIVOLT Developer RC wheel, create a MIDIVOLT-managed pinned
Text2midi Python environment (the upstream lock targets Python 3.10),
and provision a trustworthy checkpoint, REMI vocabulary and **complete**
local FLAN-T5 base encoder + tokenizer. See K8 and K12 docs.

Confirm hashes against **independently trusted** published file digests.
Computing a hash of a malicious local file does not make it safe.

\`\`\`powershell
$ckptSha = (Get-FileHash "C:\models\assets\pytorch_model.bin" -Algorithm SHA256).Hash.ToLowerInvariant()
$vocabSha = (Get-FileHash "C:\models\assets\vocab_remi.pkl" -Algorithm SHA256).Hash.ToLowerInvariant()

midivolt-compose-doctor \`
  --env "C:\models\text2midi-env" \`
  --checkout "C:\models\Text2midi" \`
  --checkpoint "C:\models\assets\pytorch_model.bin" --checkpoint-sha256 $ckptSha \`
  --vocab "C:\models\assets\vocab_remi.pkl" --vocab-sha256 $vocabSha \`
  --t5-dir "C:\models\flan-t5-local" \`
  --confirm-imports --cuda-smoke --require-cuda \`
  --confirm-model-load --model-load-timeout 1200 \`
  --out "C:\models\k15-load-smoke.json"
\`\`\`

**Security boundary:** --confirm-model-load deliberately authorizes local
checkpoint and REMI deserialization plus execution of the operator-pinned
third-party upstream model source. Do NOT run this on unknown downloads.
The command also requires --confirm-imports. Without explicit confirmation,
MIDIVOLT refuses to load the model. It does not fetch model assets or send
source/weights to a service. It does not edit the original MIDI.

To test CPU-only PyTorch, omit --cuda-smoke and --require-cuda, but model
loading on CPU may be slower. Running successful load smoke on CPU does not
predict real GPU token generation throughput.

## Results and release gate

- Exit 0: requested diagnostic steps (including strict real model loading
  when explicitly enabled) completed, with metadata JSON.
- Exit 2: invalid input, missing assets, strict checkpoint mismatch, bad
  decoder/encoder/tokenizer, subprocess failure or timeout. No success
  report created.
- Exit 3: incomplete readiness checks (metadata only, or missing required
  runtime/GPU compatibility); no fake success status.

The output distinguishes:
- trusted_checkpoint_load_requested
- operator_checkpoint_load_completed
- model_load.model_state_dict_strict_loaded
- upstream_model_imported, checkpoint_deserialized, remi_unpickled
- checkpoint_load_independently_attested = false
- actual_inference_verified = false
- commercial_release_ready = false

Independent provenance, model supply-chain verification, license clearance
and any generated music's authenticity still require external review.
Loading model weights is **not** the same as pretrained music inference.

## Automated verification

\`\`\`powershell
python -m pytest -q tests/test_composition_doctor.py tests/test_text2midi_local.py
python -m pytest -q
\`\`\`

Tests use **stubbed PyTorch/Transformers and synthetic placeholder bytes** to
execute the load-only control path without deserializing real checkpoints,
starting GPU inference or downloading models. They test opt-in barriers,
strict parameter/state loading, no MIDI output, rejection of false success,
asset alteration during subprocess execution and safe errors. They do **not**
establish authentic K15 model compatibility or benchmark data.

Next validation after a genuine K15 pass:
K8 authentic model generation (start with modest token count), K13 genuine
multi-seed benchmark, K14 independent MIDI/report replay, Cubase GUI and
human listening checks, and independent commercial rights assessment.

Keep PR #9 Draft and main untouched until explicitly authorized.
