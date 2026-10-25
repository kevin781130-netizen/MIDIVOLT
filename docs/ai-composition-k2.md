# AI Composition Engine — Knife 2: local Text2midi provider

**Status:** developer integration only. A real upstream model runner is wired to the
new `MidiGenerator` contract; pretrained model quality, Windows GPU inference,
commercial rights to particular weights/datasets, and Cubase acceptance are
**not** established by unit tests.

## What is connected

`midivolt-compose` uses the pre-existing, offline `model_adapters.generate_candidate`
Text2midi subprocess in an isolated temporary directory. The resulting
stand-alone MIDI is passed to `composition_engine.compose_candidate`, which
appends distinct model instrument tracks, maps musical beats onto the source
tempo map, and enforces source-track locks and event limits. The output is a
**candidate**, not an approved edit.

No upstream source, weights, pickle assets, or online API clients are bundled.
The implementation is MIDIVOLT-authored code under the repository's Apache-2.0
license; upstream model **source, weights, training data, and dependencies**
require their own commercial licensing review. A REMI `.pkl` asset can
execute Python code during loading; only use a verified trusted local asset.

## Example

Prepare trusted Text2midi model source, checkpoint, vocab, T5 cache, and the
upstream model's compatible independent Python environment first.
These arguments are **local paths**, not download URLs:

```powershell
midivolt-compose --source melody.mid --prompt "F major; piano arpeggios and bass" `
  --python "C:\models\text2midi\.venv\Scripts\python.exe" `
  --checkout "C:\models\Text2midi" `
  --checkpoint "C:\models\assets\pytorch_model.bin" `
  --vocab "C:\models\assets\vocab_remi.pkl" `
  --t5-dir "C:\models\flan-t5-tokenizer" `
  --candidate candidate.mid --manifest plan.json --lock 0 --seed 42

midivolt-review preview --manifest plan.json
midivolt-review apply --manifest plan.json --out approved.mid --approve
```

Repeat `--lock INDEX` to protect additional original tracks.
Candidate and manifest must be new paths; existing files are not overwritten.
The source MIDI is not modified. A separate explicit approval is mandatory.

**Musical caveat:** Text2midi is text-to-MIDI generation, not necessarily
*melody-conditioned accompaniment*. Existing source tracks are locked,
but harmonious counterpoint, stylistic match, track granularity and
instrument selection are **not** guaranteed. Its output BPM is aligned
by quarter-note positions, not acoustic similarity. For true
melody-conditioned generation, evaluate the already available Anticipatory
Music Transformer in a separate follow-up.

## Verification

```shell
python -m pip install -e ".[dev]"
python -m pytest -q tests/test_composition_engine.py tests/test_composition_local_provider.py tests/test_models.py tests/test_review_engine.py
```

`test_composition_local_provider.py` executes a real child Python process
that emits fixture MIDI (not trained inference). It covers multi-track
composition, BPM conversion, preservation of locked melody, creation of a
hash-bound proposal, explicit approval, missing assets and runner failures.
Passing these tests is **not** evidence of trained checkpoint inference or
DAW compatibility.

If the model fails or produces empty output, no candidate or manifest is
published. If the candidate is successfully written but a later manifest
write fails, the candidate may remain for manual inspection; it is never
automatically approved and never overwrites an existing file.
