# Cut 23 — pre-registered live Validation execution

This document freezes the decision **before** the new dataset scores are observed.

- Dataset: E-GMD v1.0.0 official **Validation** split, 6 performances (4 beats, 2 fills).
- Previous six performances (Cut 21) MUST be excluded by original song ID, restored from the actual prior GitHub artifact.
- Four fixed arms: `baseline`, `moderate_unfiltered`, `moderate_shape`, `conservative_shape`.
- Both shape arms share frozen feature v1 thresholds (spectral flatness >=0.22; contrast >=1.6; tail ratio <=0.66). No training based on Cut 21 or Test songs.
- Same full drum ontology and onset tolerance 50 ms for all arms. Treat raw WAV/MIDI as external CC BY 4.0 research assets only.
- No-hat negative control is mandatory. The selected arm must gain >=0.02 absolute GM42 recall, maintain GM42 precision >=0.60, avoid >0.12 hat precision drop and >0.05 overall precision drop, and introduce **no** extra false GM42 on no-hat recordings.
- Even if a candidate passes, production baseline stays untouched. Any no-hat control gap or safety failure results in **no promotion**.
- The official six-song **Test** split and all historical results stay untouched.

Single opt-in GitHub Actions run on `feat/drum-audit-20261025` collects the official Validation results. Upload *only* selection JSON and metrics JSON, **never** third-party WAV/MIDI or weights. This run does not download ADT_STR/Basic Pitch weights.

Result and execution link will be recorded in a separate results file, preserving this frozen plan.
