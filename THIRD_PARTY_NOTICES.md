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
