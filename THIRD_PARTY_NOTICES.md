# Third-party software and rights register

MIDIVOLT installs packages through Python packaging; their source code or trained weights are not copied into this repository.

| Project | Role | Upstream license | Link |
| --- | --- | --- | --- |
| pretty_midi | MIDI data handling | MIT | https://github.com/craffel/pretty-midi |
| music21 | Chord parsing / harmonic analysis | BSD-3-Clause | https://github.com/cuthbertLab/music21 |
| Spotify Basic Pitch (optional) | Audio-to-MIDI | Apache-2.0 | https://github.com/spotify/basic-pitch |
| Sawdust (standalone; **not included**) | External MIDI import/VST host | MIT | https://github.com/NeonMedusa/Sawdust |
| tsov (standalone; **not included**) | External AI-native DAW | AGPL-3.0 | https://github.com/luolianst/tsov |

The bridge emits standard MIDI files. Neither Sawdust nor tsov is an installed dependency, vendored component, or included executable. Transferring a file to a separately installed application does not itself embed its source code in MIDIVOLT. New linking, redistribution or hosted integrations require separate legal review.

The licenses of optional/transitive dependencies, corpora, sounds, models, checkpoints, training data and bundled plugins must be checked before commercial distribution. Keep full notices in builds.

**Not incorporated/downloaded by this PR:** Text2midi, Anticipatory Music Transformer, MIDI-GPT, MT3, MIDI-LLM and other pretrained models. Source license != checkpoint/training data license.

## tsov MCP boundary (experimental)

The optional client in `src/midivolt/tsov_mcp.py` and `src/midivolt/tsov_cli.py` is MIDIVOLT-owned code implementing MCP JSON-RPC. It launches an independently installed tsov process; no tsov source, checkpoints, assets or dependencies are vendored here. The tsov software retains AGPL-3.0 and may entail additional obligations if modified, combined, hosted or redistributed. Treat the process boundary as an engineering choice rather than a legal exemption; obtain counsel for the final commercial deployment model.

## Text2midi and Anticipatory Music Transformer runners

Optional external upstream source repositories (not copied, vendored or installed): [AMAAI-Lab/Text2midi](https://github.com/AMAAI-Lab/Text2midi) (MIT), [jthickstun/anticipation](https://github.com/jthickstun/anticipation) (Apache-2.0). Hugging Face pretrained model cards currently list Apache-2.0 for both [amaai-lab/text2midi](https://huggingface.co/amaai-lab/text2midi) and [stanford-crfm/music-medium-800k](https://huggingface.co/stanford-crfm/music-medium-800k). No pretrained weights, model code, MIDI datasets, or T5 tokenizer files are bundled. Text2midi vocabulary is a Python pickle; execute only trusted files. Reconfirm model weights, datasets, dependencies, media/music rights, copyright/attribution and commercial distribution obligations before shipping a binary.

## MIDIVOLT Model Hub

The optional Hugging Face client (`huggingface_hub`) is a runtime dependency only when `midivolt-hub ... --online` or `download` is used. No source models, weights, soundfonts or tokenizers are bundled. Users explicitly select an immutable revision, accept the model's advertised license, and authorize each file download. Local trust and separate downstream dataset/weight license review remain necessary. The Model Hub deliberately excludes Text2midi's `soundfont.sf2` pending a separate provenance and license review.
