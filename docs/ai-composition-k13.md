# K13 — Reproducible real Text2midi benchmark

## Measurement design

K13 uses the K8 strict-part runner (not a synthetic fallback in production).
An optional observer records the wall time of each external model call,
including model startup and checkpoint loading. This is NOT GPU-only
generation latency or notes per second in a sustained model session.

The bounded JSON suite permits 1–8 cases, each with an explicit safe id,
seed, prompt, optional zero-based GM program assignments, and optional
structure/harmony thresholds. Maximum planned subprocess calls: 96.
Every scenario is validated before creating any file or invoking a model.

Success means the entire K8 path completed, including strict GM role
metadata, source preservation, quality checks, persisted MIDI and manifest.
A rejected case remains in the denominator, with only its exception type
and broad stage recorded. Raw prompt content and stderr are not written.

Reported statistics:
- Fully passing cases / all executed cases
- Accepted roles in successful complete cases / all requested executed roles
- MIDI-returning model subprocesses / attempted subprocesses
- Mean, median, p95 full-call seconds, retries and accepted MIDI scores
- Per-case MIDI candidate, proposal, K8 acceptance report and timings

These are engineering/metadata measurements. GM programs alone do NOT prove
that the arrangement sounds musically or acoustically appropriate.

## Windows operator steps

First use K12 doctor to verify the approved managed Text2midi environment,
trusted checkpoint and REMI SHA-256 digests, local tokenizer AND FLAN-T5
encoder files. Then run a small fixed-seed benchmark suite:

\`\`\`powershell
$ckptSha = (Get-FileHash "C:\models\assets\pytorch_model.bin" -Algorithm SHA256).Hash.ToLowerInvariant()
$vocabSha = (Get-FileHash "C:\models\assets\vocab_remi.pkl" -Algorithm SHA256).Hash.ToLowerInvariant()

midivolt-compose-benchmark \`
  --confirm-inference \`
  --suite docs/benchmarks/k13-text2midi-suite.json \`
  --out-dir "C:\MIDIVOLT\benchmarks\k13-run01" \`
  --source "C:\MIDIVOLT\samples\melody.mid" --lock 0 \`
  --env "C:\models\text2midi-env" \`
  --checkout "C:\models\Text2midi" \`
  --checkpoint "C:\models\assets\pytorch_model.bin" --checkpoint-sha256 $ckptSha \`
  --vocab "C:\models\assets\vocab_remi.pkl" --vocab-sha256 $vocabSha \`
  --t5-dir "C:\models\flan-t5-local" \`
  --retry-per-part 0 --timeout 1800 --max-tokens 2000
\`\`\`

Replace every path with reviewed local assets. Compare the actual digests
to independently trusted sources. Do not load unknown REMI pickle files.
The output directory must be NEW, with an existing parent; existing files
and the source MIDI will not be overwritten. Start with one case to limit
GPU execution costs and only expand the suite after a successful run.

Example schema 1 suite:

\`\`\`json
{
  "schema_version": 1,
  "cases": [
    {"id":"piano_42", "prompt":"Add piano", "seed":42},
    {"id":"bass_43", "prompt":"Add bass", "seed":43,
     "programs":{"bass":33}}
  ]
}
\`\`\`

The full three-case sample is in docs/benchmarks/k13-text2midi-suite.json.
Case optional fields: harmonic_key, harmonic_chords,
minimum_structure_score, minimum_harmony_score. The parser refuses
missing GM selections for ambiguous roles before any inference.

Each successful case writes id.mid, id.proposal.json and id.acceptance.json.
The run writes benchmark.json with successful and failed results. A failed
case might leave partial candidate/manifest files; **no successful acceptance
is implied**, and those outputs must not be distributed as approved music.
Failure exceptions are categorized without recording sensitive stderr.

Exit code 0: all executed cases accepted; 3: some cases failed with a
published benchmark JSON; 2: invalid input or preflight. Even a passing
suite is not a signed proof of model provenance or third-party copyright
clearance.

## Automated checks versus real inference

\`\`\`powershell
python -m pytest -q tests/test_composition_benchmark.py
python -m pytest -q
\`\`\`

CI's benchmark tests use a synthetic fake provider injected into K8 to
exercise real MIDI candidate/review logic and failure accounting. They
never deserialize pretrained assets or benchmark CUDA. Real model performance,
musical accuracy, human listening, Cubase GUI verification and rights
clearance remain unverified until supplied and tested on a trusted machine.

Keep Draft PR #9; do not merge main or release a commercial Beta automatically.
