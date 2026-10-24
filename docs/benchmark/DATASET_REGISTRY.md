# Dataset Registry — Audio-to-MIDI Benchmark

Reviewed: 2026-10-23  
Purpose: track benchmark suitability and rights before data is downloaded, cached, used for model tuning, or redistributed.

## Decision labels

- **Conditional commercial candidate** — a public license appears to permit commercial use, subject to its conditions and a final provenance/asset review. This is not a legal clearance.
- **Research-only / permission required** — a non-commercial, no-derivatives, or similar restriction is stated. Do not use it in MIDIVOLT's commercial development workflow unless the rights holder grants written permission.
- **Blocked pending rights** — the available sources do not establish a sufficiently clear license, or sources conflict. Do not download/use it for the benchmark until resolved.
- **Evaluation-only** means use the material to score models; it does not automatically authorize training, fine-tuning, or redistribution.

## Recommended first benchmark pack

1. **E-GMD v1.0.0 — drums:** conditional commercial candidate. It supplies drum audio and aligned MIDI under CC BY 4.0. It is synthesized/rendered data, so it cannot replace a separate real-recording test.
2. **GuitarSet v1.1.0 — guitar:** conditional commercial candidate. It provides real guitar recordings and note-level annotations under CC BY 4.0. Preserve attribution and verify the exact upstream release.
3. **Commercially-cleared internal test set — bass, keys, vocal, real drums:** record performances specifically for MIDIVOLT or generate them from MIDI and instrument/sample assets whose commercial terms are documented. This fills the current gaps without relying on unclear or non-commercial datasets.

Keep the held-out test set separate from training/threshold tuning. Group all captures, stems, mixes and alternate versions of a song under the same source_song_id.

## Dataset-by-dataset review

| Dataset | Useful coverage | Published terms / source | Disposition for MIDIVOLT |
|---|---|---|---|
| E-GMD v1.0.0 | Drum audio + aligned MIDI; synthetic/rendered drum performance | CC BY 4.0. [Official Magenta dataset page](https://magenta.withgoogle.com/datasets/e-gmd) | **Conditional commercial candidate.** Keep attribution and release/checksum records; separately validate on real drum recordings. |
| GuitarSet v1.1.0 | Guitar audio, note onset/offset/pitch/string annotations; real performances | CC BY 4.0. [Original dataset page](https://guitarset.weebly.com/) · [v1.1.0 data card](https://huggingface.co/datasets/jhartquist/guitarset) | **Conditional commercial candidate.** Keep required attribution; pin the source release and verify all files used. |
| Slakh2100 | Multi-instrument synthetic stems + aligned MIDI | The [official Slakh page](https://www.slakh.com/) states CC BY 4.0; a [Hugging Face mirror](https://huggingface.co/datasets/projectlosangeles/Slakh2100) declares CC BY-NC-SA 4.0. | **Blocked pending rights.** Conflicting source declarations; verify the canonical release and underlying MIDI/audio rights before use. Do not assume a mirror inherits the official site's terms. |
| MusicNet | Classical multi-instrument audio and note-level labels/reference MIDI | [Zenodo record](https://zenodo.org/records/5120004) describes freely licensed recordings and labels, but the record's exact license string is not clear in the retrieved metadata. | **Blocked pending rights.** Confirm terms for the exact audio, MIDI and label files separately. Domain is classical chamber music, not modern band stems. |
| URMP | Real, isolated instrument recordings, MIDI scores and note annotations; 44 pieces | [Official Rochester project page](https://labsites.rochester.edu/air/projects/URMP.html) describes the assets; an explicit reuse license was not located on that page. | **Blocked pending rights.** Ask the dataset maintainers for written commercial-use permission before using it. Valuable real-performance supplement if cleared. |
| MAESTRO v3.0.0 | High-quality piano audio + aligned MIDI; ~3 ms alignment; 1,276 performances / ~198.7 h | CC BY-NC-SA 4.0. [Official Magenta page](https://magenta.withgoogle.com/datasets/maestro) | **Research-only / permission required.** Do not use in commercial development absent separate permission. |
| MAPS | Piano audio + reference MIDI, synthesized and Disklavier recordings | CC BY-NC-SA 2.0 (France). [Official project page](https://adasp.telecom-paris.fr/resources/2010-07-08-maps-database/) | **Research-only / permission required.** Do not treat a differently licensed derivative or metadata package as relicensing the audio. |
| IDMT-SMT-Drums | 608 WAV files, ~2 h 10 min; kick/snare/hi-hat onset annotations | CC BY-NC-ND 4.0 for evaluation. [Fraunhofer IDMT](https://www.idmt.fraunhofer.de/en/publications/datasets/drums.html) | **Research-only / permission required.** No commercial workflow until written permission covers the intended evaluation/use. |
| IDMT-SMT-Bass | ~4,300 isolated bass-note WAV files, ~3.6 h, multiple playing/expression techniques | CC BY-NC-ND 4.0 for evaluation. [Fraunhofer IDMT](https://www.idmt.fraunhofer.de/en/publications/datasets/bass.html) | **Research-only / permission required.** Strong diagnostic set, not cleared for commercial development. |
| IDMT-SMT-Bass-Single-Track | 17 bass lines with note onset/offset/pitch and playing-style annotations | CC BY-NC-ND 4.0 for evaluation. [Fraunhofer IDMT](https://www.idmt.fraunhofer.de/en/publications/datasets/bass_lines.html) | **Research-only / permission required.** Small evaluation set; not cleared for commercial development. |
| MDB Drums | Drum annotations + audio for 23 MedleyDB tracks | CC BY-NC-SA 4.0. [Project repository](https://github.com/CarlSouthall/MDBDrums) | **Research-only / permission required.** Not cleared for a commercial benchmark without separate permission. |
| MIR-1K | Singing voice + accompaniment, pitch contours, voiced/unvoiced and segment annotations; 1,000 short clips | Zenodo record marks access as restricted and asks users to contact the author; no clear license for commercial use. [Zenodo record](https://zenodo.org/records/3532216) | **Blocked pending rights.** Do not use a public mirror as proof of permission. Also note: pitch contours are not full MIDI note-event ground truth. |

## What this means for the five MIDIVOLT stem types

- **Drums:** start with E-GMD for a reproducible synthetic baseline; build a separately licensed real-recording test set. Do not place IDMT or MDB assets in the commercial benchmark until cleared.
- **Bass:** the available high-value IDMT sets are marked non-commercial/no-derivatives. Use self-recorded/licensed bass stems for the first commercial test set; resolve MusicNet/Slakh only for the specific intended use.
- **Guitar:** GuitarSet is the best clear-license starting point in this list, subject to attribution and pinned-version review.
- **Keys:** MAESTRO and MAPS are useful research benchmarks but are not cleared for commercial use. Use a self-generated, rights-documented piano/keyboard set for the commercial gate.
- **Vocal:** no fully-cleared, human vocal note-event MIDI dataset has been established in this review. MIR-1K is restricted and supplies pitch contours rather than full MIDI note events. Create a consented, self-recorded set or obtain a written commercial license.

## Release gate

No dataset is marked **commercially cleared** by this registry alone. Before use, record the exact release/version, source URL, download date, checksum, audio license, annotation/MIDI license, underlying-work provenance, attribution text, and a reviewer decision. Do not upload datasets or samples to this repository; keep only metadata and hashes here.

This registry is an engineering due-diligence record, not legal advice.
