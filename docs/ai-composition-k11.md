# K11 — actual Windows 3.11 wheel build + clean install acceptance

## Decision

K11 bridges the gap between the K10 **synthetic archive** tests and a
**real Windows-installed CLI developer release candidate**.

Verified in a real GitHub-hosted `windows-latest`, Python 3.11 environment:
- `python -m build --wheel --outdir dist` generated the actual
  `midivolt-0.1.0rc1-py3-none-any.whl`.
- A read-only inspection of the built wheel passed the K10 beta gate:
  wheel metadata/console entrypoints, legal notices, PEP 427 RECORD
  hashes/sizes and unsafe-asset exclusions.
- A new independent Python 3.11 virtualenv installed the actual wheel
  and its third-party runtime dependencies; the offline MIDI smoke created
  and analyzed MIDI, reviewed+approved a proposed arrangement, produced
  Cubase-compatible Type 1 SMF, and checked exact MIDI event parity.
- A Windows ZIP was created with the wheel, installer, smoke script,
  readme and legal notices; K10 verified checksum, strict membership
  and that the wheel's bytes matched the independently built wheel.
- The ZIP was unpacked into a fresh location and the packaged PowerShell
  installer created a second new venv and ran the smoke suite.
- The ZIP, its SHA256 manifest, wheel-content audit and ZIP-content audit
  are uploaded together as a workflow artifact.

Initial **actual** Windows K11 job:
[Windows Developer RC run 40176155246](https://github.com/kevin781130-netizen/MIDIVOLT/actions/runs/40176155246)
passed these steps on development commit `55b645f2b1384c0363354482b59343705e6b1d2a`.

K11 additionally expands `Smoke-MIDIVOLT.ps1` to validate the console
entrypoints added across K1–K10, including `midivolt-compose`,
`midivolt-compose-accept`, `midivolt-compose-audit`,
`midivolt-beta-gate` and analysis/transcription help commands. Check
the latest feature-branch Windows Developer RC run before asserting
that this expanded check passed.

## How a Windows user installs the verified artifact

From the successful job page, download the attached
`MIDIVOLT-Windows-0.1.0rc1` ZIP artifact. It contains the outer install
ZIP and its checksum file. Preserve both files and confirm the digest:

```powershell
(Get-FileHash .\MIDIVOLT-Windows-0.1.0rc1-py311.zip -Algorithm SHA256).Hash.ToLowerInvariant()
Get-Content .\MIDIVOLT-Windows-0.1.0rc1-py311.zip.sha256
```

The output digest must match the independently trusted checksum.
Extract the inner ZIP, review the scripts and licensing, and only then
select one dependency source:

```powershell
# Explicitly authorize pip network dependency downloads:
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Install-MIDIVOLT.ps1 -AllowNetwork

# Or use pre-reviewed and complete dependency wheelhouse, without pip network:
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Install-MIDIVOLT.ps1 -Wheelhouse D:\audited-wheels
```

Windows Python 3.11 (including the Python Launcher `py.exe`) must be
installed independently. The installer refuses to overwrite the target,
and it does not include a Python distribution, a pretrained checkpoint,
Cubase, a GUI or any VST3 plugin.

## Release scope

The working **developer CLI RC is installable**. The following remain
hard blockers for a commercial AI-composition Beta:

- Trusted real pretrained Text2midi inference and instrument adherence
- Human auditory evaluation of actual generated parts
- Cubase GUI import, playback and re-export under actual DAW settings
- Independent clearance of pretrained model, dataset and generated music rights
- Independent dependency provenance, vulnerability and publishing/signing review

Green fixture suites, a successful wheel build, an installed CLI, and a
passed SMF roundtrip alone cannot satisfy those release gates. Keep the
development PR Draft; don't tag/publish a commercial Beta or merge to
`main` merely from an installability result.

## Workflow and repeatability

The existing `.github/workflows/windows-rc.yml` is temporarily scoped
to the integration branch **or PR #9**, so the feature branch can be
tested without merging to main. The job performs wheel+ZIP actual build,
content audit, isolated install, offline smoke and packaged installer
verification, then retains a 30-day artifact. This runs ordinary
GitHub-hosted CI (not the user's Windows desktop).

The workflow's package tests execute no external AI model; the
K8/K9 acceptance tools remain usable after local provisioning.
