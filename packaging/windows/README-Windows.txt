MIDIVOLT Windows Developer Release Candidate 0.1.0rc1
===================================================

This ZIP is a Python wheel and PowerShell installer, NOT a Windows GUI app.
Python 3.11 x64 must be installed already, with the Windows py.exe launcher.
No pretrained AI model, GPU framework, Steinberg Cubase or VST3 instrument is included.

The ZIP contains MIDIVOLT's own wheel, not its third-party dependency wheels.
Installation requires you to choose one dependency source explicitly:

Online:  PowerShell -NoProfile -ExecutionPolicy Bypass -File .\Install-MIDIVOLT.ps1 -AllowNetwork
Offline: PowerShell -NoProfile -ExecutionPolicy Bypass -File .\Install-MIDIVOLT.ps1 -Wheelhouse D:\audited-wheels

Only run trusted PowerShell files from the verified release artifact.
The installer creates a NEW per-user venv and refuses to overwrite a pre-existing
directory. Installation is not administrator-dependent. Network mode permits pip
to download dependencies from configured package indexes; offline mode uses only
the provided wheelhouse. An offline wheelhouse must contain every required dependency.

The installer invokes Smoke-MIDIVOLT.ps1 after pip installation. This
executes local MIDI generation, analysis, proposal lock/approve, Model Hub
offline catalog, Cubase Type 1 conversion and semantic event comparison.
It does not install or run any external pretrained model or Cubase.

Default installation path:
%LOCALAPPDATA%\MIDIVOLT\venv-0.1.0rc1

Help:
%LOCALAPPDATA%\MIDIVOLT\venv-0.1.0rc1\Scripts\midivolt.exe --help
%LOCALAPPDATA%\MIDIVOLT\venv-0.1.0rc1\Scripts\midivolt-review.exe --help
%LOCALAPPDATA%\MIDIVOLT\venv-0.1.0rc1\Scripts\midivolt-cubase.exe --help

STATUS: Developer-only RC; model checkpoint inference, Cubase GUI playback
and native VST3 are not certified. Model Hub/model environments are opt-in.
Review THIRD_PARTY_NOTICES.md and LICENSE before commercial distribution.
