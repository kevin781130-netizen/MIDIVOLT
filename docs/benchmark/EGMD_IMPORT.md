# E-GMD human-performed electronic-drum benchmark import

## Source and usage decision

**Official source:** https://magenta.withgoogle.com/datasets/e-gmd  
**Version:** E-GMD v1.0.0 (Google Magenta, CC BY 4.0, attribution required).

This release has 444+ hours and 43 kit renderings of human drummer
performances on Roland equipment. The WAV audio was re-recorded from
performance MIDI on the electronic Roland TD-17. It includes both
acoustic-sounding kits and electronic-sounding kits but is **NOT**
direct-microphone acoustic-drum recordings.

The official full WAV+MIDI ZIP is approximately **90 GB** (132 GB unpacked).
Do **not** auto-download this into GitHub Actions or commit this dataset
to MIDIVOLT. The published SHA-256 of the full archive is:

    7d9a264fb4c9eabd9fec09d5f8e333192f529b1a1b845d170279a977ac436053

The MIDI-only archive is ~103 MB; it does not provide the WAV inputs
necessary to score transcription. The official page also offers a small
standalone CSV metadata download.

**Current status:** E-GMD is a declared CC BY 4.0 source,
NOT yet approved in MIDIVOLT's per-file benchmark manifest.
The importer creates rights records with `status: pending`.
A real reviewer must confirm the exact audio, MIDI, attribution
and underlying rights before marking any record approved.

## First: select a sample without downloading the 90 GB archive

Download *only* e-gmd-v1.0.0.csv from the official page, then run:

    python -m midivolt.egmd_import       --csv /data/e-gmd/e-gmd-v1.0.0.csv       --data-root /data/e-gmd       --output /data/e-gmd/selection_plan.json       --mode plan       --max-performances 12       --kits-per-performance 2

The JSON plan includes source performance, style, BPM, kit identity,
relative WAV/MIDI paths and whether the files are present locally.
It selects from the original upstream **test split only**, using
a stable seed and style/beat-type round-robin; no held-out sample is
promoted from a train or validation split.

Every kit rendering of an underlying performance shares
one `source_song_id`. Hence if you choose two different kits
from one performance, song-macro averaging still counts that performance
as **one** source song. Do not evaluate a chosen test performance
after using the same MIDI notes to tune the model.

## Then: obtain only the selected pairs

The public E-GMD files ship in a large archive, not individually on the
official dataset page. Acquire the needed ZIP or an **officially
authorized** extracted copy, verify release checksums, extract the
selected WAV/MIDI files under the same dataset root, and rerun
`--mode plan` to confirm all selected pairs are present.

This importer intentionally does not offer a hidden remote downloader
or fabricate paths when files are missing.

## Produce a rights-review manifest

When all files are present:

    python -m midivolt.egmd_import       --csv /data/e-gmd/e-gmd-v1.0.0.csv       --data-root /data/e-gmd       --output /data/e-gmd/manifest.json       --mode review-manifest       --max-performances 12       --kits-per-performance 2

The importer will fail if a selected WAV or MIDI is missing or leaves
the dataset root via path traversal/symlink. It computes SHA-256 hashes
for both files. The generated manifest remains intentionally **blocked**
until the human rights reviewer updates `rights.status` to
`approved`, enters their actual reviewer name, and sets
`rights.commercial_benchmark_allowed` to true, based on
documented permissions. Do not change these values without review.

## Compare the engines after approval

    python -m midivolt.drum_suite       --manifest /data/e-gmd/manifest.json       --output /data/reports/e-gmd-dsp       --engines dsp

For ADT_STR, use the previously documented *research-only* local
checkout/checkpoint workflow and add `--engines dsp adt_str`.
The benchmark reports all kit renderings and both engines separately.

The output has **three disjoint audio domains**:

- `real_recording`: separately obtained, direct-microphone real acoustic drums
- `electronic_kit_recording`: E-GMD's human performances on electronic sampled drumkits
- `synthetic_rendered`: programmatically generated smoke fixtures

The field `real_recordings_present` stays false for an
E-GMD-only benchmark; `electronic_kit_recordings_present`
records its availability. **Do not combine their F1 values into
one headline score**.

## Roland MIDI note mapping (important)

Some original Roland TD-11 reference MIDI pitches differ from GM.
When the E-GMD importer adds `reference_midi_mapping`:
`roland_td11_to_gm`, the scoring pipeline applies these
explicit corrections **to an in-memory copy of the ground truth only**:

| Original Roland MIDI pitch | GM drum pitch |
|---|---:|
| 22, Hi-hat closed edge | 42 |
| 26, Hi-hat open edge | 46 |
| 58, Tom 3 rim | 43 |

All other pitches are preserved, including 37 Side Stick, 38 Snare
and 49 Crash. Scoring remains exact-GM-pitch, 50 ms onset tolerance.
The raw MIDI, WAV and their SHA-256 hashes remain unchanged.

The test output additionally includes conservative onset-based
WAV/MIDI **alignment quality diagnostics**: estimated delay,
dispersion and cases requiring human review. No test-set MIDI or
model prediction is automatically shifted, quantized or corrected
to improve accuracy.

## Next evidence gate

E-GMD is the first professionally annotated human-performance,
**electronic-kit** test lane. A direct acoustic drum dataset with
matching commercially cleared MIDI remains necessary before making
claims about live, microphone-recorded drums.

Keep test-set recordings isolated from training, hyperparameter tuning,
threshold selection, and manual error correction.
