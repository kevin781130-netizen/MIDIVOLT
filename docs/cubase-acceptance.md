# Cubase MIDI Acceptance — Standard MIDI File (SMF) Type 1

MIDIVOLT now has a **DAW-neutral MIDI event audit** designed to make Cubase
import/export less fragile. This is not a Steinberg plugin, nor a claim that
Cubase has been launched in CI.

Steinberg documents that Cubase imports Standard MIDI Files (SMFs) and that
import settings affect track layout, master tempo and controllers:
- [Cubase Pro 15 MIDI Import Options](https://www.steinberg.help/r/cubase-pro/15.0/en/cubase_nuendo/topics/importing_audio_and_midi/importing_audio_and_midi_import_options_for_midi_files_r.html)
- [Cubase 15 Exporting Standard MIDI Files](https://www.steinberg.help/r/cubase-artist/15.0/en/cubase_nuendo/topics/track_handling/track_handling_exporting_midi_tracks_as_standard_midi_file_t.html)

## Step 1 — Preflight any generated or source MIDI

\`\`\`powershell
midivolt-cubase check --input approved.mid
\`\`\`

The report includes format type, PPQ, track/note counts, tempo/measure/key
events, CC, pitch bends, SysEx, misplaced master events and warnings.

## Step 2 — Prepare a safe separate MIDI Type 1 export

\`\`\`powershell
midivolt-cubase prepare --input approved.mid --out cubase-import.mid --ppq 480
\`\`\`

- Creates **a new file** and refuses all overwrites, including original.
- Preserves every standard MIDI event and its tick location after explicit
  PPQ scaling. Creates a Type 1 SMF with tempo, meter and key on track 0;
  Type 0 messages are split by channel while preserving channel 10 for drums.
- Program change, CC, pitch bend, SysEx, markers and other SMF events are
  retained. Exact source-vs-export event multiset equality is checked before
  publication, and the saved file is reopened for a second integrity check.
- If the requested PPQ would collapse a positive-duration note to zero ticks,
  aborts instead of introducing broken notes. A change from very high PPQ to
  480 may still quantize sub-tick onset precision, clearly noted in the report.
- This protects the **MIDI event data** representable as SMF; proprietary
  Cubase VST/audio tracks, clip colors, plug-in state, DAW-specific information
  and effects are not part of the MIDI interchange contract.

If the input is Type 1 / 480 PPQ, the exporter still verifies and relocates
misplaced conductor events without altering the source file.

## Step 3 — Manually import in Cubase (Windows acceptance)

1. Open Cubase and use **File → Import → MIDI File**. This avoids confusing a
   drag-and-drop MIDI event workflow with standard file import.
2. In **Preferences → MIDI → MIDI File**, turn off **Import Dropped File as Single
   Part** if using drag-and-drop and separate tracks are desired.
3. If importing into an *existing* Cubase project and you want the file's own
   tempo map, disable **Ignore Master Track Events on Merge**. With it enabled,
   imported MIDI follows the existing project tempo.
4. Choose controller handling appropriate to the project. **Import Controller
   as Automation Tracks** may move CC to automation lanes.
5. Confirm note count/pitches, velocity, source tempo (e.g., 70 BPM), time
   signatures, CC/pitch bend and tracks. MIDI synth programs are not a promise
   that Cubase will load a specific instrument plugin automatically.
6. Re-export from Cubase using **File → Export → MIDI File**, ensuring the
   intended tempo, signature, controllers and Type 1 tracks are included.

Cubase 15's documented import preferences are authoritative for Cubase; the
application UI, terminology and location can vary by version and license.

## Step 4 — Compare Cubase re-export with MIDIVOLT reference

\`\`\`powershell
midivolt-cubase compare --reference cubase-import.mid --returned cubase-roundtrip.mid
midivolt-cubase compare --reference cubase-import.mid --returned cubase-roundtrip.mid --strict
\`\`\`

Compare uses exact **musical tick positions** despite different PPQ values.
It includes non-note MIDI events (CC, programs, tempo, meter, markers), so
intentional Cubase changes may show a mismatch. The report counts events
added/missing; \`--strict\` exits code 3 if content differs. **Even a strict
match doesn't prove the exact Cubase GUI imported the file:** a human must
record the installation/version and successful import separately.

## Windows and real model acceptance status

- Windows GitHub Actions runs the \`pytest\` suite for MIDI format 0/1, PPQ
  conversion, tempo relocation, controller/SysEx preservation, immutable input
  and strict event comparison. It does **not** start Cubase.
- \`midivolt-accept\` is the earlier explicit real-model inference acceptance
  entry point. It requires the separately installed, pinned upstream runtime
  and model weights and reports real inference only if an actual generated
  candidate passes melody-lock review. No pre-trained weights are bundled or
  downloaded by these Cubase tests.
- Cubase 13/14/15 GUI/manual smoke, real model checkpoint/GPU inference and
  VST3 playback remain **separate unverified acceptance items**.
- A reported RMX → Cubase "time type mismatch" during drag/drop may be a
  drag/drop clip representation problem rather than an invalid SMF. Try an
  actual exported \`.mid\` through File → Import and compare the resulting SMF
  before modifying unrelated Cubase project settings.
