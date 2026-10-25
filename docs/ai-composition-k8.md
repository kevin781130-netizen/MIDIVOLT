# K8 — real pretrained-model acceptance + commercial rights gate

**Scope:** execute a genuine, user-provisioned pretrained Text2midi checkpoint
through **the complete K1–K6 strict per-part path**, not a fixture model.
K7 Linux/Windows Core MIDI CI passing does **not** establish this milestone.

## Result / environment

- K8 code provides an **operator-controlled** acceptance entrypoint.
- No real 902 MB Text2midi checkpoint, REMI pickle or upstream Python
  environment is provisioned in this PR's GitHub Actions.
- Consequently, **real pretrained inference is not verified here**. A
  successful test of this entrypoint using a mocked provider is a *unit test*,
  not an inference or commercial release certificate.
- No model weights or upstream source are bundled, downloaded automatically,
  or added to git. Never run untrusted checkpoints or vocabulary pickle files.

## Preflight

Use the existing `midivolt-hub inspect text2midi --online` and
`midivolt-env plan/create/install/verify` workflow to pin the checkout commit
and install upstream dependencies into an independently managed environment.
Always verify provenance and executable Python before running the model.

On a trusted Windows workstation, compute **actual local** digests:

```powershell
(Get-FileHash "C:\models\assets\pytorch_model.bin" -Algorithm SHA256).Hash.ToLowerInvariant()
(Get-FileHash "C:\models\assets\vocab_remi.pkl" -Algorithm SHA256).Hash.ToLowerInvariant()
```

Set the resulting values as the two SHA-256 arguments; they must be independently
compared with a trusted origin, not merely copied from untrusted local bytes.

```powershell
midivolt-compose-accept `
  --confirm-inference `
  --env "C:\models\text2midi-env" `
  --checkout "C:\models\Text2midi" `
  --checkpoint "C:\models\assets\pytorch_model.bin" `
  --checkpoint-sha256 "<64 lowercase hex from trusted checkpoint>" `
  --vocab "C:\models\assets\vocab_remi.pkl" `
  --vocab-sha256 "<64 lowercase hex from trusted vocabulary>" `
  --t5-dir "C:\models\flan-t5-tokenizer" `
  --source melody.mid --prompt "鋼琴、小提琴" --lock 0 `
  --harmonic-key "C major" --seed 42 `
  --retry-per-part 0 --timeout 1800 `
  --candidate candidate.mid --manifest proposal.json --report acceptance.json
```

For ambiguous roles (e.g., bass) provide explicit `--program bass=32`.
Using `--retry-per-part 0` on the *first* authentic run is recommended to
avoid repeatedly loading a large checkpoint before feasibility is known.

The following must happen before an acceptance report is created:

1. Explicit `--confirm-inference` (there is no implicit fallback).
2. Managed environment pinned to a specific, clean upstream git commit, plus
   unchanged requirements hash.
3. SHA-256 of both the local checkpoint and unpickled-on-inference REMI
   vocabulary must match the supplied trusted digests **before and after**
   model execution.
4. The Text2midi runner's actual subprocess produces notes. Each requested
   instrument is checked for program, drum classification, MIDI structure,
   optional harmonic constraints, and locked original-track invariants.
5. A new MIDI candidate and hash-bound proposal are written, reloaded and
   compared to the in-memory review; only then is a new JSON report saved.

No output file is overwritten. A crash after candidate writing may leave a
candidate/manifest **without** a success report. Treat that as an incomplete
run, not acceptance; use fresh filenames for a rerun.

The JSON report records elapsed time, pinned source commit, requirements hash,
checkpoint/vocabulary hashes, MIDI hashes, note counts, per-part diagnostics
and failure-to-release flags. It does **not** approve the generated MIDI;
separate `midivolt-review apply ... --approve` remains mandatory.

## Commercial rights: evidence versus unresolved clearance

| Component | Publicly advertised terms | Commercial conclusion |
| --- | --- | --- |
| MIDIVOLT K1–K8-authored composition modules | MIDIVOLT Apache-2.0 repository | Implementation intended for commercial integration |
| Text2midi upstream source | MIT on GitHub | Permissive, retain appropriate license notices |
| `amaai-lab/text2midi` pretrained checkpoint | Hugging Face model card: Apache-2.0 | Permissive model-card label; does not certify outputs or underlying song rights |
| MidiCaps training data | Hugging Face dataset: CC BY-SA 4.0 | Attribution/share-alike obligations and composition rights require expert review |
| SymphonyNet pretraining data | Referenced by Text2midi model card | Independent licensing/rights investigation required |
| Original Lakh MIDI content underlying MidiCaps | Lakh site: CC BY 4.0 distribution; scraped MIDI | Distribution label does not independently prove third-party composition copyright clearance |
| T5 tokenizer and upstream Python dependencies | Their own licenses | Review and pin exact versions before redistribution |

Sources checked October 25, 2026:

- Text2midi source: https://github.com/AMAAI-Lab/Text2midi
- Model card/weights: https://huggingface.co/amaai-lab/text2midi
- Dataset card: https://huggingface.co/datasets/amaai-lab/MidiCaps
- Lakh MIDI original project: https://colinraffel.com/projects/lmd/

**Commercial_release_ready stays false by design.** A permission/license label
alone is not a legal opinion or a guarantee against memorization, output
similarity or infringement. Documented rights review, real benchmark runs,
listening/harmonic evaluation, and Cubase workstation imports are separate gates.

## Tests

```shell
python -m pytest -q tests/test_composition_acceptance.py
python -m pytest -q
```

These are **fake-provider contract tests**: consent requirements, pinned asset
checksums, clean failure/no report, non-overwrite, source preservation,
persisted report integrity and CLI failure behavior. They do not run trained
model weights, execute GUI Cubase, or adjudicate copyrights.
