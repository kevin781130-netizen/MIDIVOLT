# E-GMD mini research pilot — real human electronic-kit performances

**Run date:** 2026-10-25  
**Model test:** https://github.com/kevin781130-netizen/MIDIVOLT/actions/runs/40145844048  
**Short-lived JSON artifact:** https://github.com/kevin781130-netizen/MIDIVOLT/actions/runs/40145844048/artifacts/12581230788  
**Model:** ADT_STR setting-tau-0.8, revision a33c5c6b191a4ca1e0f6dc22140947485eb36ce8  
**Source:** Google Magenta E-GMD v1.0.0, CC BY 4.0, Test split  
**Protocol:** 50 ms exact GM percussion pitch, one-to-one onset matching, no quantization or timing corrections.

## Measured results

| Metric | DSP v1 | ADT_STR |
|---|---:|---:|
| Human-performance electronic-kit excerpts | 3 | 3 |
| Source-song groups | 3 | 3 |
| Inference failures | 0 | 0 |
| Truth drum events | 38 | 38 |
| True positives | 17 | 16 |
| False positives | 19 | 15 |
| False negatives | 21 | 22 |
| Precision | 0.472222 | 0.516129 |
| Recall | 0.447368 | 0.421053 |
| **Event-micro F1** | **0.459459** | **0.463768** |
| **Song-macro F1** | **0.460000** | **0.465635** |
| Median model-call time | 0.0058 s | 1.9047 s |
| p95 nearest rank (n=3) | 0.0066 s | 42.9557 s |
| Median real-time factor | 0.0031 | 1.0317 |

The ADT_STR p95 includes a large first-call initialization/warm-up
effect: do not present that as stable inference latency. Model load
separately reported as 0.059 s, and CPU-only runtime was
Python 3.11.17 with PyTorch 2.8.0+cpu.

### Per-clip F1

| Official performance ID | Genre | Duration (metadata) | DSP | ADT_STR |
|---|---|---:|---:|---:|
| drummer1/session2/167 | afrocuban/rhumba | 1.932 s | 0.480000 | 0.545455 |
| drummer1/session2/30 | country | 1.956 s | 0.500000 | 0.434783 |
| drummer1/session1/259 | funk/purdieshuffle | 1.846 s | 0.400000 | 0.416667 |

All three excerpts used the TD-17 **Acoustic Kit** rendering,
not actual acoustic-drums microphone recordings. They are separate
performance IDs but all from drummer1, so performer diversity is zero.
These are *very short fills*, not complete commercial songs.

### Error diagnostics

- DSP: Kick GM36 F1 **0.500000**, with 14 false-positive kick
  events; Snare GM38 F1 **0.740741**; no GM37/40 or tom/ride
  reference note was correctly transcribed.
- ADT_STR: Kick GM36 F1 **0.923077**, with 1 missed kick and no
  false-positive kick events; Snare GM38 F1 **0.640000**,
  Open Hi-hat GM46 F1 **0.666667**; tom/ride labels still poor.
- Kick/Hi-hat/Tom/Ride note family labels are not merged in the primary
  score. GM Crash was absent from ground truth, so **Crash accuracy
  is unmeasured**, not zero.
- Alignment QC: two excerpts reported no large uniform offset
  (median +2.029 ms and +8.695 ms); one was
  `insufficient_confident_events` and must not be described
  as proven time-aligned by the diagnostic.

### Source integrity and rights

The official E-GMD full ZIP is 90 GB; the GitHub runner used HTTP 206
Range requests to extract exactly the selected WAV/MIDI entries from
the canonical Google Storage ZIP. It did **not** fetch the full archive.

Per-excerpt WAV SHA-256:

- drummer1/session2/167:
  `c8dd3fefbd62d351a62a9e48333e5601ee5d55f2b5674795c1aabfd86843f712`
- drummer1/session2/30:
  `60f620a0b077a6d0f9f1275e03a016eaa9e80d5f0a70aeb04f6035003e85305e`
- drummer1/session1/259:
  `382fe3e3400642440edb251115d28d70b426fe1889a1338b35cce37bea7f213f`

Those hashes identify the extracted audio bytes. The 90GB original
archive checksum is from the **official publication**, not independently
recomputed during this small Range extraction. The corresponding exact
MIDI hashes and full selection are in the GitHub run artifact.

The dataset is published by Google LLC under CC BY 4.0.
Cite: Lee Callender, Curtis Hawthorne, Jesse Engel,
*Improving Perceptual Quality of Drum Transcription with the Expanded
Groove MIDI Dataset* (2020), E-GMD v1.0.0.

ADT_STR's weight and commercial deployment rights remain under review.
**No WAV, MIDI or model checkpoints were published in this repository.**

## Decision

**Neither DSP nor ADT_STR is ready to be advertised as high-accuracy
drum transcription from this evidence.** Numerical ADT_STR advantage
is negligible at three snippets and not robust. DSP is many times
faster on this test; ADT_STR makes fewer false kicks but needs better
coverage and reliable warm-run latency measurement.

Next meaningful work: select longer held-out beats and different drummers
if upstream split allows; score at least dozens of recordings with
various kits and actual acoustic microphones as a separate benchmark;
measure velocity and time errors, including Ghost Notes and cymbals.
Do not tune a model on these held-out test performances and then
report their tuned score as unbiased.
