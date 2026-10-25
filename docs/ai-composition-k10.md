# MIDIVOLT K10 — Beta release package gate (fail closed)

## Decision

K10 is a **packaging and security audit for a Python developer RC**, not an
authorization to ship a commercial AI-arrangement Beta. No current source
fixture, successful unit test, green GitHub Actions workflow, wheel or ZIP
can prove that real Text2midi weights worked, that Cubase actually imported
the generated MIDI, or that third-party song rights have been cleared.

The new `midivolt-beta-gate` inspects the **actual built artifacts** without
executing embedded files, contacting any server, downloading packages,
loading model checkpoints or opening Cubase. The command does not build
an artifact for you; `--wheel` must be a real wheel file.

## Build and check a developer wheel on a trusted Windows Python 3.11

No GitHub Actions workflow quota is required for this workflow.
Run separately in PowerShell:

```powershell
py -3.11 -m pip wheel . --no-deps --no-build-isolation -w dist
$wheel = (Get-ChildItem dist\midivolt-*.whl | Select-Object -First 1).FullName
py -3.11 -m midivolt.beta_gate_cli --wheel $wheel --developer-rc --out dist\beta-package-audit.json
```

`--no-build-isolation` requires locally installed and reviewed
setuptools/wheel; pip won't download dependencies in this command, but the
preinstalled build backend still executes. If there are older files in
`dist`, move/remove them before building so `$wheel` is unambiguous.

Alternatively, after installing MIDIVOLT in a controlled environment,
use the installed `midivolt-beta-gate` console command.

The developer-wheel acceptance checks that:

- The wheel is a valid, non-overlarge, pure Python (`py3-none-any`)
  MIDIVOLT archive, with PEP metadata for Python 3.11.
- **Both** Apache-2.0 `LICENSE` and `THIRD_PARTY_NOTICES.md` exist
  within the wheel's `.dist-info/licenses/` directory and contain
  suitable headings. K10 updates `pyproject.toml` to include them.
- The critical command names and **their exact entrypoint targets** exist,
  and all declared MIDIVOLT CLI modules are actually packaged.
- The package has no unexpected model checkpoint, unsafe pickle,
  soundfont or media payload.
- Archive member paths are safe, entries are unique, and uncompressed
  size is bounded, reducing accidental packaging mistakes.

**Passing `--developer-rc` proves artifact-content checks only.** It does
not imply a clean-environment install or runtime execution.

## Optional Windows RC installer archive

The existing Windows RC workflow is limited to the `integration/`
branch. PR #9 uses a different feature branch, so that Windows ZIP
build/smoke job is **skipped**; K10 does not relabel it as passed.

When a trusted ZIP, the corresponding separately built wheel, and the
independently published checksum are available:

```powershell
midivolt-beta-gate --developer-rc `
  --wheel dist\midivolt-0.1.0rc1-py3-none-any.whl `
  --windows-zip dist\MIDIVOLT-Windows-0.1.0rc1-py311.zip `
  --zip-sha256 "paste-64-lowercase-hex-digest-from-trusted-release-manifest" `
  --out dist\windows-package-audit.json
```

The ZIP must contain the exact wheel bytes, installer, smoke script,
readme, LICENSE and third-party notices. The digest must match the
independently supplied value. This confirms integrity of the submitted
files, not the trustworthiness of the source of the digest, signature,
dependencies or Windows PowerShell execution.

## Commercial Beta mode — intentionally returns nonzero

```powershell
midivolt-beta-gate --wheel dist\midivolt-0.1.0rc1-py3-none-any.whl
```

Exit status:
- `0`: `--developer-rc` was explicitly selected and package-content
  checks passed; this is **not** Beta clearance.
- `2`: Malformed, missing, tampered or unacceptable distribution artifact.
- `3`: The package contents passed, but commercial Beta remains blocked.

The JSON output explicitly shows:
`developer_package_content_verified=true`,
`developer_rc_install_verified=false`,
`commercial_beta_release_ready=false`.
The blockers are not auto-cleared by a self-authored JSON assertion.

## Release-blocker matrix

| Release requirement | Current K10 evidence | Gate |
| --- | --- | --- |
| Cross-platform Python 3.11 fixture CI | Core MIDI tests K9 passed 217/217 with one skip per OS | Verified as code tests, not actual model |
| Pure Python wheel contents / console scripts / bundled legal notices | K10 validation is available; **must run on built artifact** | Pending actual artifact |
| Clean Windows wheel installation and PowerShell smoke | Existing workflow filtered out for PR #9 | Pending |
| Genuine pinned Text2midi weights through K8 inference | Requires operator-controlled trusted local assets | Blocked |
| Generated voice quality and human musical listening | Heuristic MIDI scores do not substitute for listening | Blocked |
| Cubase GUI import/playback/export | Offline SMF comparisons cannot establish GUI use | Blocked |
| Model weights, training data and generated-music rights | MidiCaps/SymphonyNet/Lakh terms require independent review | Blocked |
| External dependency, install-chain and release-signing security | Not established by wheel-content inspection | Blocked |

Do not merge PR #9, tag an AI Beta, or ship model assets based only on
green unit tests. **Real inference, DAW acceptance and legal approval are
release gates rather than claims we can manufacture in CI.**

## Test

```powershell
py -3.11 -m pytest -q tests/test_beta_gate.py
py -3.11 -m pytest -q
```

These tests construct synthetic archives to exercise path traversal,
duplicate entries, CLI module mismatch, missing licenses, embedded
unsafe models, ZIP payload and digest mismatch, no-overwrite reports and
exit codes. They do **not** pretend to be packaging/install or model
runtime acceptance.
