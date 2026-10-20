# MIDIVOLT: Text2midi + Anticipatory Music Transformer (experimental)

These are **real code-path model runners**, not placeholders. MIDIVOLT calls the upstream Transformer classes and model generation functions in separate, user-provided Python environments. **No weights or dependencies are bundled or automatically downloaded.**

| Model | Source/license | Model weights/license | Role |
| --- | --- | --- | --- |
| [AMAAI-Lab/Text2midi](https://github.com/AMAAI-Lab/Text2midi) | MIT | [amaai-lab/text2midi](https://huggingface.co/amaai-lab/text2midi) Apache-2.0 | Text description to MIDI |
| [jthickstun/anticipation](https://github.com/jthickstun/anticipation) | Apache-2.0 | [stanford-crfm/music-medium-800k](https://huggingface.co/stanford-crfm/music-medium-800k) Apache-2.0 | Melody-conditioned accompaniment |

MIDIVOLT currently uses Python 3.11. Install each upstream repository and its documented requirements into **independent** environments with the Python/PyTorch/Transformers versions that upstream supports. Check the actual weights/dataset/third-party sample terms before commercial redistribution. The code is separately authored, not copied from upstream, and there is no automatic downloading.

## Text2midi: original melody + new AI tracks

Manually obtain the upstream checkout, model checkpoint file \`pytorch_model.bin\`, \`vocab_remi.pkl\`, and a local tokenizer directory for \`google/flan-t5-base\`. Provision while online; MIDIVOLT inference runs with Hugging Face offline flags. **The REMI vocabulary is a pickle that can execute code when read: only use assets from a verified, trusted origin.**

Example Windows PowerShell (replace paths with your local ones):

\`\`\`powershell
midivolt-model text2midi --python "C:\models\text2midi\.venv\Scripts\python.exe" --checkout "C:\models\Text2midi" --checkpoint "C:\models\text2midi-assets\pytorch_model.bin" --vocab "C:\models\text2midi-assets\vocab_remi.pkl" --t5-dir "C:\models\flan-t5-tokenizer" --prompt "F major, 70 BPM, romantic youthful piano and synth flute, no drums" --source melody.mid --out candidate.mid --manifest plan.json --lock 0
midivolt-review preview --manifest plan.json
midivolt-review apply --manifest plan.json --out approved.mid --approve
\`\`\`

Text2midi can also generate stand-alone MIDI without \`--source\`. A reviewed proposal requires \`--source\`, \`--manifest\` and at least one explicit \`--lock\`.

## Anticipatory Music Transformer: melody-conditioned accompaniment

Manually obtain \`stanford-crfm/music-medium-800k\` (local Transformers directory containing \`config.json\` and checkpoint weights). Install [the anticipation package](https://github.com/jthickstun/anticipation) in its independent environment.

\`\`\`powershell
midivolt-model anticipation --python "C:\models\anticipation\.venv\Scripts\python.exe" --checkout "C:\models\anticipation" --checkpoint "C:\models\music-medium-800k" --source melody.mid --melody-program 73 --seconds 12 --top-p 0.98 --out accompany.mid --manifest accompany.json --lock 0
midivolt-review preview --manifest accompany.json
midivolt-review apply --manifest accompany.json --out approved.mid --approve
\`\`\`

The \`--melody-program\` is a **0-based General MIDI program** (73 = flute). Upstream conditioning selects MIDI events by program, so if several tracks share it, they can all be conditioning inputs. A model-generated accompaniment is appended to the original MIDI rather than replacing its original tracks. Timing of new notes is translated by quarter-note position to the source tempo map (e.g. generated 120 BPM onto source 70 BPM). This preserves locked material but does **not** guarantee stylistic, harmonic or temporal quality.

## Protection, acceptance, limitations

- You must select the model Python binary, upstream checkout and checkpoint paths explicitly; subprocess uses \`shell=False\`, timeout (default 1200 seconds) and offline environment flags.
- Output files and proposal manifest cannot already exist. Generation runs into a temporary MIDI, validates it, then writes the candidate.
- Existing melody MIDI tracks, CC and pitch bend remain copied unchanged. Source tempo, meter and key maps are preserved. The existing review engine hashes the MIDI files, computes note diffs and requires a separate \`--approve\` before publication to another new MIDI.
- Text2midi model's upstream CLI has hardcoded paths; the adapter intentionally invokes the **published model class** instead of that upstream CLI.
- Heavy GPU inference **has not been run** in the available sandbox. \`tests/test_models.py\` runs a **fake model script in a genuine child Python process** to test the subprocess, merging, timing/locks, proposal review, failures and output paths, not real pretrained weights.
- Models load code and assets from explicitly trusted local directories. Neither upstream code nor Python pickle checkpoints should be treated as a sandbox boundary. Never run untrusted assets as administrator.
- Tokenizer/model library versions can change; pin a tested upstream commit and its environment once real Windows/GPU acceptance succeeds.
- MIDI metadata not represented by \`pretty_midi\` (e.g. proprietary DAW metadata/SysEx) can be lost in generated candidate files. Original source files remain intact.
- Cubase VST3 integration, realtime inference, model quality evaluation and GPU throughput benchmarking are still future milestones.

**Smoke test:** \`python -m pytest -q tests/test_models.py\`.
