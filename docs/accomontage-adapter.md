# AccoMontage external MIDI adapter — cut 4 (experimental)

**Status:** SOURCE_ONLY / NO_MODEL_RUN / COMMERCIAL_RIGHTS_BLOCKED.
This bridge adds no model, weights, downloaders, new dependencies or GUI.
It reuses MIDIVOLT's candidate/proposal/review engine. Main branch remains unchanged.

## Trust boundary

- Code: [AccoMontage](https://github.com/zhaojw1998/AccoMontage) has an MIT software license.
- Weights/checkpoints, POP909-derived data, and donor musical material have **unverified commercial/redistribution rights**. MIT source code licensing is **not** evidence of rights to every model or musical asset.
- **Never** execute an unverified `.pt`, pickle, or NumPy `allow_pickle=True` payload in a privileged account. Upstream code uses `torch.load` and NumPy object arrays. Run any separately approved inference only in an isolated environment with verified, pinned assets.
- This module does not import/run upstream Python, load any checkpoints, retrieve data, call networks, or automatically publish MIDI. It only validates local MIDI and creates a **review proposal**.
- The adapter is **not** an isolation sandbox for executing upstream code.

## Operator workflow — two explicit steps

Install MIDIVOLT in its usual Python 3.11 environment. Create your own MIDI with a distinct lead melody and chord track, with fixed tempo, 4/4 meter, and matching phrase segmentation.

1. Stage a non-destructive, two-track lead sheet for an operator-controlled upstream run:

```powershell
python -m midivolt.accomontage_adapter prepare --source "C:\music\lead.mid" --workdir "C:\music\acco-stage-001" --melody-track 0 --chord-track 1 --segments A8B8
```

`--workdir` must not exist yet. The command creates only `lead sheet.mid` and `request.json`; the input is never rewritten. `lead sheet.mid` keeps source tempo/maps but contains only the selected melody and chord tracks. The staged melody is always **upstream track 0**. For the original AccoMontage notebook, the folder is its `SONG_NAME` under `DEMO_ROOT`. This adapter does not run the notebook.

2. **Only after** you have independently verified upstream assets/rights and run the external engine, manually identify the actual accompaniment track in its output MIDI (never choose the returned melody). Import it:

```powershell
python -m midivolt.accomontage_adapter ingest --request "C:\music\acco-stage-001\request.json" --generated "C:\music\external-output.mid" --accompaniment-track 1 --out "C:\music\candidate.mid" --manifest "C:\music\proposal.json"
midivolt-review preview --manifest "C:\music\proposal.json"
# Only after listening and human approval:
midivolt-review apply --manifest "C:\music\proposal.json" --out "C:\music\approved.mid" --approve
```

The import **appends exactly one chosen, pitched accompaniment track** to the original MIDI and uses the existing musical-beat alignment; it does not import the engine's copy of the melody. The original melody track is locked, source/lead-sheet SHA256 hashes are validated, source tempo/meter/key remain unchanged, output paths must be new, and approval is a separate command. A successful `ingest` does **not** assert audio quality, inference correctness or commercial redistribution permission.

## Explicit v1 limitations

- Only constant **4/4** and single fixed tempo. No pickup, automatic phrase segmentation, mixed meters, tempo curves, or source-vs-generated acoustic timing guarantee. The phrase string must exactly cover the source's MIDI bars. Valid phrases are letter + 1–16 bars (e.g. `A8B8`).
- The input requires distinct nonempty pitched melody and chord tracks. The adapter does not analyze audio, synthesize sounds, generate chords, run trained weights, or preserve third-party model metadata.
- The external output has to be inspected by a human to select the actual accompaniment track. Wrong track selection is not a model-quality guarantee; keep original tracks and visually/audibly inspect before approval.
- The merged file is an SMF, not a Cubase project; effects, VSTs and production mix settings are not included.
- Existing MIDIVOLT MIDI review checks preserve locked original events and global tempo/meter/key maps, but some vendor-specific MIDI metadata can be lost in MIDI reconstruction.
- All local tests are **synthetic MIDI contract tests**. External checkpoint inference, model authenticity, Windows and Cubase real-machine acceptance remain **NOT_RUN**.

## Regression command

```powershell
python -m pytest -q tests/test_accomontage_adapter.py tests/test_models.py tests/test_review_engine.py
```

No GitHub Actions or release pipelines are required by this cut. No production claim until tests, source verification, human review and real-machine acceptance have been recorded.
