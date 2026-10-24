# ADT_STR real weights versus MIDIVOLT DSP — first measured run

Date: 2026-10-24  
Status: **real PyTorch inference completed, research only**  
Workflow: https://github.com/kevin781130-netizen/MIDIVOLT/actions/runs/40094732624  
Artifact: https://github.com/kevin781130-netizen/MIDIVOLT/actions/runs/40094732624/artifacts/12560671009

## Actual execution

- **Source model:** Pierfrancesco/adt-str, `setting-tau-0.8`.
- **Source SHA:** `77dbef225e7029478ebfb916f20c7a00274f0f12`.
- **Hugging Face revision:** `a33c5c6b191a4ca1e0f6dc22140947485eb36ce8`.
- **Downloaded weight SHA-256:** `f94d1773d929166e0a3f63d305975aa6667512f8a71d7706872e1f8b23ca930b` (verified locally after download).
- **Weight size:** 289,134,056 bytes.
- **Python:** 3.11.17, Torch 2.8.0+cpu, GitHub Actions x86_64 Linux CPU.
- **No external weights committed**, shared, or included in downloadable job artifacts.
- Hub model-card `license` metadata was **null** at the pinned revision. Upstream GitHub code README states CC BY-SA 4.0, but the exact weight rights and product implications remain a **commercial-release blocker**.

## Dataset

**2.8-second machine-generated mono drum WAV with exact reference MIDI.**
Six events: 2 Kick GM36, 1 Snare GM38, 3 Closed Hi-hat GM42.
One Kick and Hi-hat are simultaneous. A single, short, deterministic
synthesized fixture cannot predict accuracy for live drummers.

## Fair matched-event comparison

One-to-one, exact GM pitch, 50 ms onset tolerance. Both engines used the
**same WAV and the same reference MIDI**. Outputs were not manually edited
or quantized.

| Metric | DSP v1 | ADT_STR tau=0.8 |
|---|---:|---:|
| Reference events | 6 | 6 |
| Predicted events | 6 | 6 |
| True positives | 6 | 5 |
| False positives | 0 | 1 |
| False negatives | 0 | 1 |
| Precision | 1.000 | 0.833333 |
| Recall | 1.000 | 0.833333 |
| F1 | **1.000** | **0.833333** |
| Matched onset MAE | 2.6459 ms | 4.4649 ms |
| Kick F1 (2 reference) | 1.000 | 1.000 |
| Snare F1 (1 reference) | 1.000 | 0.000 |
| Closed hat F1 (3 reference) | 1.000 | 0.857143 |

ADT_STR missed the isolated Snare, and produced one extra closed-hat event
on this waveform. That is a **failure case to investigate**, not evidence
that DSP is universally more accurate.

## Measured performance (single run, not warmed benchmark)

| Metric | DSP | ADT_STR |
|---|---:|---:|
| Model download | none | 6.140 s (reported separately) |
| Model load | n/a | 0.031 s |
| Inference on 2.8 s audio | 0.004 s | 0.643 s |
| Inference real-time factor | 0.001 | 0.230 |
| Cold total, excluding download | 0.004 s | 0.673 s |

Timing is one CPU-only trial. Do not extrapolate speed to long songs or
claim comparable GPU performance. The model was pinned by SHA, not by a
moving `main` tag.

## Acceptance decision

- DSP: continue as opt-in, lightweight commercial-candidate **baseline**.
- ADT_STR: confirmed executable and accurate enough to produce structured
  GM percussion MIDI on a synthetic probe, but **research-only** while
  licensing and real-recording evaluation remain unresolved.
- Neither model has passed a real drum performance benchmark or a
  full commercial legal review.

## Next action

Get a rights-cleared, instrument-isolated drum recording with its
time-aligned GM reference MIDI, including kick/snare/hat/toms/rides/crashes,
velocity variation, softer ghost notes, simultaneous hits and multiple
tempi. Run each engine unchanged, compare per-piece F1 and speed over
multiple songs, and make a commercial decision only afterward.
