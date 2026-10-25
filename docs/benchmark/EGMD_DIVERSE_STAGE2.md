# E-GMD Diverse Held-out Evaluation — Stage 2

Scope: extend the 3-clip (~2-second) smoke to 6 distinct performances: 4 long 8–35 second grooves plus 2 short 1–7 second fills, requiring at least 3 drummers.

Upstream: E-GMD v1.0.0 official test split, human drumming reproduced on Roland TD-17 electronic drum kits; not acoustic microphone recordings.

Sampling is deterministic and metadata-only, before observing any new model output. E-GMD's long clips are predominantly beats, so fills are selected in a separate short-duration stratum. Selection scores reward new drummers, beat/fill diversity, primary styles and tempo ranges. No train or validation clips can be substituted for missing Test clips.

## Two-stage controlled execution

1. Metadata plan: GitHub workflow egmd-diversity-plan.yml; no ZIP access or weights. Trigger one-off with commit marker [egmd-plan-once].
2. Full A/B: GitHub workflow egmd-mini-research.yml; 6 WAV+MIDI pairs through ZIP HTTP Range, no 90GB download; explicitly triggered by [egmd-real-once], not routine CI.

Outputs retain source performer IDs and durations, WAV/MIDI hashes, approximate onset alignment evidence, per-GM-pitch F1, song macro/micro F1 and timed CPU inference. The official Test split is never used for model threshold adjustment.

Models are unchanged. No improvement in F1 is claimed without results. ADT_STR checkpoint is research-only pending a separate full commercial review.

## What is still required for a reliable release decision

A substantially larger dataset with every claimed percussion family, multiple kits and performers, and held-out acoustic microphone recordings. Longer clips and more performers strengthen diagnosis but do not alone prove product readiness.
