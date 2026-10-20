# MIDIVOLT isolated model runtime and real-checkpoint acceptance

**Milestone:** reproducible model-specific environments, separated from the MIDIVOLT
Python 3.11 core and each other. This slice implements working commands but
**does not** install Python itself, automatically fetch models, or declare GPU
inference successful without actually executing a model.

Text2midi and Anticipatory pin incompatible Transformer requirements (4.47.0
vs 4.29.2), so never install both in the same venv. Text2midi's upstream
requirements were generated with Python 3.10. Use a locally installed,
trusted Python **3.10** executable for Text2midi; Python 3.10 or 3.11 is
supported by the environment manager for Anticipatory, subject to upstream
dependency wheel availability.

## 1. Plan a pinned checkout and create an isolated environment

Clone each model repository *separately*, inspect its actual source revision
and review its requirements file before installation:

\`\`\`powershell
git -C "C:\models\Text2midi" rev-parse HEAD
git -C "C:\models\Text2midi" status --short
Get-Content "C:\models\Text2midi\requirements.txt"

# No network, no files written by the plan:
midivolt-env plan text2midi --checkout "C:\models\Text2midi" --revision APPROVED_SOURCE_COMMIT_SHA40 --base-python "C:\Python310\python.exe" --env "C:\MIDIVOLT\Environments\text2midi"

# Creates one NEW venv path; no pip/model downloading:
midivolt-env create text2midi --checkout "C:\models\Text2midi" --revision APPROVED_SOURCE_COMMIT_SHA40 --base-python "C:\Python310\python.exe" --env "C:\MIDIVOLT\Environments\text2midi" --confirm-create
\`\`\`

Plan/create refuses an existing environment, edited tracked upstream files, a
non-matching Git commit, a checkout missing the expected entry point, or a venv
inside the checkout. On creation MIDIVOLT records the pinned Git SHA,
\`requirements.txt\` SHA256, interpreter version and destination in a local
\`.midivolt-model-env.json\`. It never silently overwrites or upgrades a venv.
An interrupted \`create\` may leave a partial directory for **manual**
inspection/removal, instead of potentially deleting other user content.

Anticipatory follows the same command sequence with:
\`anticipation --checkout "C:\models\anticipation" --env "C:\MIDIVOLT\Environments\anticipation"\`
and its **own** approved source commit and base interpreter.

## 2. Explicit dependency installation (opt-in)

Preview and audit the upstream requirements file first. Pip can install
packages that execute code as part of installation; do not use unknown
checkouts or untrusted wheels.

Network installation (only after explicit confirmation):

\`\`\`powershell
midivolt-env install --env "C:\MIDIVOLT\Environments\text2midi" --allow-network --confirm-install
\`\`\`

Or use a curated offline wheelhouse (no package index/network by command):

\`\`\`powershell
midivolt-env install --env "C:\MIDIVOLT\Environments\text2midi" --wheelhouse "D:\audited-wheels" --confirm-install
\`\`\`

The installer runs \`<venv-python> -m pip install -r <checkout>/requirements.txt\`
after rechecking the Git SHA and requirements digest. It uses \`shell=False\`.
A one-time install refusal prevents accidental in-place upgrades. Installed
package versions from \`pip freeze\` are stored in the venv manifest. This
does **not** make unpinned transitive dependencies perfectly reproducible;
fully locked wheel hashes and model-specific GPU builds are later milestones.
On failure inspect the partial environment; do not assume it's clean.

## 3. Verify safely, optionally import trusted upstream modules

\`\`\`powershell
midivolt-env verify --env "C:\MIDIVOLT\Environments\text2midi"
midivolt-env verify --env "C:\MIDIVOLT\Environments\text2midi" --run-imports
\`\`\`

Default verify checks source commit, requirements digest and interpreter.
\`--run-imports\` **executes trusted upstream Python modules** and inspects
Torch/Transformers versions and CUDA detection; use it only after reviewing the
source. A successful import check is NOT proof of checkpoint correctness.

## 4. Real checkpoint end-to-end acceptance

After provisioning weights and tokenizer with the guarded Model Hub (and
reviewing their origin), use \`midivolt-accept\`. This launches the **actual**
Text2midi/Anticipatory Runner, reopens its generated MIDI, verifies the locked
melody, writes an immutable proposal and a structured acceptance JSON.

\`\`\`powershell
midivolt-accept text2midi --env "C:\MIDIVOLT\Environments\text2midi" --checkout "C:\models\Text2midi" --checkpoint "C:\models\assets\pytorch_model.bin" --vocab "C:\models\assets\vocab_remi.pkl" --t5-dir "C:\models\flan-t5-tokenizer" --prompt "F major, 70 BPM, youthful romantic piano and synth flute, no drums" --source melody.mid --lock 0 --out candidate.mid --manifest proposal.json --report real-smoke.json --confirm-inference
midivolt-review preview --manifest proposal.json
midivolt-review apply --manifest proposal.json --out accepted.mid --approve
\`\`\`

Anticipatory uses the same acceptance tool with
\`midivolt-accept anticipation --env ... --checkout ... --checkpoint LOCAL_MODEL_DIR
--source melody.mid --melody-program 73 --seconds 12 --lock 0
--out candidate.mid --manifest proposal.json --report real-smoke.json
--confirm-inference\`.

The report records actual elapsed inference time, pinned upstream Git SHA and
requirements digest, locked-track review, candidate file SHA256 and note
counts. It sets \`real_inference_completed=true\` **only when the real Runner
has produced valid new notes**. It intentionally leaves musical quality,
weight provenance, GPU throughput benchmarking and Cubase import as **not
verified**. A mocked unit test may exercise report formatting but does not
replace this acceptance.

## Safety and limitations

- This is **not** automatic Python installation or a no-prompt one-click model
  download. The user supplies an already installed interpreter, audited Git
  checkout and local model assets.
- Model dependencies are installed only after \`--confirm-install\` and either
  an explicit network opt-in or an offline wheelhouse selection.
- PyTorch, model code, pickle tokenizer/checkpoint, training datasets and
  copyright/soundfont rights require independent review before commercial
  product shipping.
- The venv manager validates source version and requirements hash; it does not
  validate remote Git signatures or automatically trust any commit.
- The runtime may require CUDA GPU drivers and an appropriate PyTorch build.
  No GPU smoke is performed automatically in CI.
- MIDIVOLT core's \`pytest\` suite does not fetch model weights or invoke
  pretrained inference. Run \`pytest -q tests/test_environments.py\` to check
  real isolated venv creation and offline dependency installation on CI.

Source: [Text2midi](https://github.com/AMAAI-Lab/Text2midi),
[Anticipatory Music Transformer](https://github.com/jthickstun/anticipation).
