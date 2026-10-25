# K12 — actual Text2midi runtime readiness (no pretrained inference)

## Root cause discovered and resolved in the model runner

The published AMAAI-Lab Text2midi Transformer calls
T5EncoderModel.from_pretrained("google/flan-t5-base") inside its constructor.
The old MIDIVOLT integration supplied a *local tokenizer* directory but
did not guarantee the **FLAN-T5 encoder config and model weights** were
available offline. With HF_HUB_OFFLINE=1 this can fail before generating a
single note, even if Text2midi weights and vocabulary are valid.

K12 now requires a local folder that contains BOTH the T5 tokenizer and
encoder assets, including:
- tokenizer_config.json and config.json with model_type=t5
- nonempty model.safetensors (preferred), model.safetensors.index.json plus
  all shards, or pytorch_model.bin / index plus all shards.

When the pinned upstream Transformer requests precisely
"google/flan-t5-base", MIDIVOLT's runner redirects that specific request
to the supplied T5 folder, with local_files_only=True. Requests for a
different encoder ID fail closed. No upstream code is patched on disk or
vendored, and nothing is downloaded automatically.

The upstream pinned constructor and generate() functions are inspected via
Python's AST without importing untrusted upstream source. If its constructor
no longer makes the expected FLAN-T5 request, acceptance stops and requires
manual review.

**Security:** Local safetensors are preferred. PyTorch .bin checkpoints and
the REMI pickle must come from reviewed, trusted sources. SHA-256 comparison
against a digest computed from the *same* untrusted file is not independent
provenance. Model weights are never bundled with the MIDIVOLT CLI wheel.

## Operator command — inspect without loading a model

First create/install/verify the pinned model environment as described in K8.
Then on the trusted model workstation:

\`\`\`powershell
$checkpointSha = (Get-FileHash "C:\models\assets\pytorch_model.bin" -Algorithm SHA256).Hash.ToLowerInvariant()
$vocabSha = (Get-FileHash "C:\models\assets\vocab_remi.pkl" -Algorithm SHA256).Hash.ToLowerInvariant()

midivolt-compose-doctor \`
  --env "C:\models\text2midi-env" \`
  --checkout "C:\models\Text2midi" \`
  --checkpoint "C:\models\assets\pytorch_model.bin" \`
  --checkpoint-sha256 $checkpointSha \`
  --vocab "C:\models\assets\vocab_remi.pkl" \`
  --vocab-sha256 $vocabSha \`
  --t5-dir "C:\models\flan-t5-local" \`
  --out "C:\models\doctor-metadata.json"
\`\`\`

This mode checks pinned source/requirements, SHA-256 assets, tokenizer and
encoder structure, package metadata and Python version WITHOUT importing
torch/transformers or the upstream model. It returns exit code **3** (not
fully ready) because API import compatibility has not been tested.

To opt into actual package imports and a **tiny CUDA tensor calculation**:

\`\`\`powershell
midivolt-compose-doctor \`
  --env "C:\models\text2midi-env" \`
  --checkout "C:\models\Text2midi" \`
  --checkpoint "C:\models\assets\pytorch_model.bin" \`
  --checkpoint-sha256 $checkpointSha \`
  --vocab "C:\models\assets\vocab_remi.pkl" \`
  --vocab-sha256 $vocabSha \`
  --t5-dir "C:\models\flan-t5-local" \`
  --confirm-imports --cuda-smoke --require-cuda \`
  --out "C:\models\doctor-cuda.json"
\`\`\`

A smoke test verifies a small CUDA matrix multiplication, torch.load's
weights_only API and T5Tokenizer presence. It also reports installed
PyTorch/Transformers versions, CUDA build version, GPU capability, memory
availability and a tiny operation's elapsed milliseconds. **These are
compatibility diagnostics, NOT Text2midi tokens/sec, VRAM requirements,
musical accuracy or proof that the pretrained checkpoint runs.**

Without --require-cuda, CPU-only PyTorch can pass the explicit import check,
but K8 inference might be slow. The CUDA flags require --confirm-imports.

## Result meanings

- Exit **0**: provided assets and requested import/CUDA checks passed, so
  an **attempt** at real-model K8 inference is allowed; no trained weights
  have been loaded.
- Exit **2**: invalid, missing, mismatched or unsafe preflight inputs, or
  runtime subprocess failure; no success JSON is created.
- Exit **3**: diagnostic JSON generated with explicit compatibility blockers
  (missing Python dependencies, no requested CUDA compute, metadata-only).

The diagnostic report always leaves actual_inference_verified,
commercial_release_ready, upstream_model_imported and remi_unpickled **false**.
The runner is sandboxed by offline environment flags but cannot guarantee
that arbitrary user-supplied upstream model code is safe to execute.
Use only trusted, pinned external checkouts and model assets.

## Test limitations and next gate

\`\`\`powershell
python -m pytest -q tests/test_text2midi_local.py tests/test_composition_doctor.py tests/test_composition_acceptance.py
python -m pytest -q
\`\`\`

K12 tests use synthetic placeholder files, stubbed device status, and static
AST fixtures. They verify that unexpected encoder downloads, missing T5
weights/shards, model source drift, mismatched hashes and unconsented GPU
checks cannot silently pass. They **do not** run a real pretrained checkpoint,
evaluate music, launch Cubase or clear copyright rights.

References checked in the upstream source:
https://github.com/AMAAI-Lab/Text2midi/blob/main/model/transformer_model.py
and its Python 3.10 requirements.txt.

PR #9 remains Draft, main remains untouched. K8 genuine checkpoint inference,
K9 Cubase application roundtrip/human review, and third-party rights review
remain explicit commercial Beta blockers.
