# MIDIVOLT 0.1.0rc1 — Windows developer release

This is a **CLI developer release candidate**, not a packaged DAW, standalone
Windows GUI, VST3, preinstalled pretrained model, or Cubase plugin.

## Code integration

Integration branch: `integration/windows-rc1-20261020`. It descends from
the previous seven stacked Draft PRs (#1→#7) and contains all their changes.
Review the **single RC Draft PR against main** instead of individually merging
the stacked drafts. No change is merged to `main` automatically.

The consolidated code includes:
- MIDI creation/analysis/arrangement and lossless-source write protections.
- Sawdust and tsov Standard MIDI bridges; tsov external MCP agent integration.
- Melody-locked AI candidate review → explicit approval → new MIDI export.
- Text2midi and Anticipatory model runners with opt-in local checkpoints.
- HF Model Hub catalog/search/verified file download and pinned model venv manager.
- Cubase-facing SMF Type 1 export, controller preservation and strict event compare.
- Windows/Ubuntu pytest matrix, additional clean wheel install/CLI smoke on Windows.

## Build and get the Windows RC ZIP

The [Windows Developer RC GitHub Actions workflow](https://github.com/kevin781130-netizen/MIDIVOLT/actions/workflows/windows-rc.yml)
runs on integration branch pushes, using Python 3.11 on GitHub's Windows
runner. It builds the project wheel, installs it into a fresh virtualenv,
runs MIDI generation/review/Cubase interoperability smoke, then uploads the
release ZIP **and a separate .sha256 file** under
`MIDIVOLT-Windows-0.1.0rc1` (artifact expires after 30 days).

Unzip to a non-admin directory and verify the ZIP's SHA256 using
`Get-FileHash .\MIDIVOLT-Windows-0.1.0rc1-py311.zip -Algorithm SHA256`
against the uploaded checksum text before trusting installer scripts.

**No Python interpreter or third-party dependency wheelhouse is bundled.**
The ZIP contains a MIDIVOLT wheel, installer, smoke test and license notices.
This avoids redistributing pretrained model weights or unreviewed runtime
bundles in a first RC. It is not an offline turnkey application installer.

## Install on Windows

Prerequisite: trusted Python **3.11 x64** registered with `py.exe`.

After extracting the ZIP:

```powershell
# Installs MIDIVOLT and retrieves normal PyPI dependencies from configured indexes.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Install-MIDIVOLT.ps1 -AllowNetwork

# Alternative with separately provisioned, audited dependency wheels, no index:
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Install-MIDIVOLT.ps1 -Wheelhouse "D:\audited-wheels"
```

Default path: `%LOCALAPPDATA%\MIDIVOLT\venv-0.1.0rc1`. You can supply
`-Destination "C:\some-new-folder\midivolt"`. The installer refuses to
replace an existing path; the scripts **do not require admin rights**.
Pip may install and execute dependency build code in the new user venv;
review your dependency sources. Only run installer scripts from the official
artifact you have verified.

After installing, it immediately runs `Smoke-MIDIVOLT.ps1`, which checks:
- MIDI `create` and `analyze`, offline Model Hub catalog.
- Arrangement proposal with track lock, preview and approved export.
- Cubase Type 1/480 PPQ MIDI export and strict semantic event equality.
- Console script entry points for the optional model/tsov/environment tools.

Smoke tests generate only temporary MIDI and do not start any real pretrained
model, download weights, connect tsov, or launch Cubase.

## Commercial and quality acceptance gates still open

**Not yet verified by these automated tests**:
- Genuine Text2midi / Anticipatory checkpoint loading, musical output or GPU
  performance on a real Windows computer.
- Cubase 13/14/15 GUI import, plugins, real playback, or the RMX drag/drop
  time-type mismatch.
- Audio output, VST3 plugin packaging, Windows GUI distribution, signed installer.
- Model training dataset/weight/soundfont rights and final distribution review.
- Arbitrary network/pip package source trust, antivirus and security hardening.

Use `midivolt-accept` for a real pretrained model test after independently
reviewing and provisioning the model, and `midivolt-cubase compare` after
manually importing/re-exporting with Cubase.

The previous Draft PRs are left open for traceability until the integrated RC
has completed its checks. Do not merge them individually into main if the
consolidated PR is selected.
