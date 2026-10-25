# K14 — Offline evidence replay after the real-model benchmark

## Purpose

K13 writes \`benchmark.json\` containing per-model-call timings, per-part
attempts, successes and failures. **Do not treat the summary JSON alone as
independently checked evidence.** K14 rereads every successful K8 case and
uses the actual K9 strict MIDI audit to compare source MIDI, candidate,
manifest, SHA-256 hashes, GM programs, preserved original tracks and
structural/harmony metrics. It recalculates K13's aggregate totals and
timing statistics instead of trusting the stored values.

This is a verification of **artifact integrity and statistical consistency**.
Neither K8, K9 nor K14 cryptographically proves that authentic pretrained
Text2midi weights were executed. It does not launch Cubase or authorize
copyright/licensing release.

## Run without GPU, internet, checkpoint loading or unpickling

After running an authentic K13 benchmark on your trusted machine:

\`\`\`powershell
midivolt-compose-verify \`
  --benchmark "C:\MIDIVOLT\benchmarks\k13-run01\benchmark.json" \`
  --out-dir "C:\MIDIVOLT\benchmarks\k14-verification01"
\`\`\`

Optionally bind an existing K12 runtime preflight report to the successful
K8 cases' model source commit, checkpoint SHA-256, vocabulary SHA-256 and
upstream dependency requirements SHA-256:

\`\`\`powershell
midivolt-compose-verify \`
  --benchmark "C:\MIDIVOLT\benchmarks\k13-run01\benchmark.json" \`
  --doctor "C:\MIDIVOLT\benchmarks\doctor-imports.json" \`
  --out-dir "C:\MIDIVOLT\benchmarks\k14-verification02"
\`\`\`

The output folder **must be new**, and the existing K13 evidence remains
read-only. Each accepted K8 MIDI receives a separately persisted K9 audit
file. A final \`verification.json\` is saved only after all cross-checks pass.

K14 checks:
- K13 case counts, fail-fast subset status, successful and failed
  denominators, exception class counts and model-call return rates
- per-call nonnegative finite durations, mean, median and p95 summary
- unique safe case IDs, fixed source/candidate/manifest paths
- K8 source and candidate SHA-256, one-to-one accepted role track ordering,
  source track locks and K5/K6 MIDI scores (through K9 replay)
- per-role accepted/rejected attempt entries, seeds, rejection categories
  and call-duration joins with recorded provider observations
- same checkpoint, REMI vocabulary, pinned upstream commit and requirements
  across successful cases; optionally compare these to K12 doctor.

K14 exit codes: 0 if the *entire declared suite* completed and all cases
passed MIDI/report replay; 3 if the summary is internally valid but some
cases failed or execution ended early; 2 for invalid/tampered evidence,
missing MIDI, invalid doctor provenance or unsafe output paths.

An accepted full suite is **not** a commercial release certificate.
K14 JSON fields for external model execution proof, Cubase GUI operation,
independent human listening, commercial rights and release readiness
stay false by design.

## Tests

\`\`\`powershell
python -m pytest -q tests/test_composition_benchmark.py
python -m pytest -q
\`\`\`

Tests generate synthetic MIDI via the K13 test fixture provider to prove
the replay checks and failure handling. They do NOT measure pretrained
Text2midi accuracy, GPU speed, Cubase usability or verify music rights.

Recommended remaining real-workstation sequence:
1. K12 doctor with verified local FLAN-T5 encoder and runtime/CUDA imports.
2. K13 genuine checkpoint benchmark, limited initial cases and zero retries.
3. K14 offline integrity replay of every accepted output.
4. Manual Cubase GUI MIDI import/re-export, music quality listening,
   independent license/security review before any commercial Beta release.

The main branch remains unchanged; keep PR #9 Draft until explicit approval.
