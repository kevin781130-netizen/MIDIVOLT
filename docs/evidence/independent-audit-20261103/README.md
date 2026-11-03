# Independent MIDI RC audit — 2026-11-03

PRE_DEVICE_RC_READY for core MIDI CLI only. Windows/PowerShell parser/Cubase NOT_RUN.
Branch: fix/midivolt-rc-closeout-python313-gates-20261102
Starting SHA: 5a9cf5b154b2aa42c69d6565d4022eca52b78b15
Tested source SHA: 12c59e329afda6818df26f9e103fb04629dc19c1
Fix commits: 9f717a10001e3679f5eea893fcf24eadad6abd67, fb5004e, 12c59e329afda6818df26f9e103fb04629dc19c1
Evidence commit: the commit introducing this directory (separate from tested source).
Existing checkout and main untouched; detached isolated worktree /workspace/midivolt-audit. No AGENTS.md found in checkout/parent. No Actions or release.

## Confirmed P1 and repair
Strict compare ignored order of Type 0 channel and global conductor events: reversed same-tick note-off/on or two tempos incorrectly returned exact_event_match=true. before.log demonstrates both regression failures on original code (pytest exit 1). Added ordered Type 0 channel and global metadata/SysEx streams to supplement existing Counter, lane and duration checks. prepare now verifies order before publication. Type 1 within-lane checks remain and whole-track permutations are still accepted. The first broad implementation broke an existing permutation test; corrected without weakening tests. affected.log: final 18 passed. Intermediate gate*.json are superseded by final-gate*.json, all on final tested source.

## Results
- Python 3.11.17: 336 passed, 4 skipped; pinned clean-tree formal gate PASS_PRE_MACHINE, exit 0.
- Python 3.12.14 / 3.13.16: 331 passed, 9 skipped each. All seven stages PASS, overall formal status BLOCKED EXPECTED_HEAD_REQUIRED_FOR_RELEASE, exit 2 by design. This is not full release certification for these versions. Final pytest logs retain skip reasons. Pytest 9 reports 5 additional passing subtests.
- Source contract, offline AI regression, real music21, wheel build/integrity/clean install PASS on all three versions. Real music21 acceptance exercises Bb7/Eb slash body/bass, harmony/key/arrangement, not just import.
- Final wheel independently installed noneditable in /workspace/rc-clean, no system-site-packages, unset PYTHONPATH/PYTHONHOME, commands executed from /tmp. pip check PASS. installed-probe.json records installed import path/version/13 entry points. entrypoints.json records all 13 actual --help command outputs/exits.
- workflow.json: installed generate/propose/preview/approve/check/prepare/strict compare, PPQ 192/480/960, Chinese/space paths, locked note/CC/bend/program semantics, source hash unchanged, output conflict refusal.
- independent_probe.py: installed Type 0/1 prepare, independent mido absolute-event readback, controller/bend/program/drum channel/SysEx/tempo/retrigger/tail preservation; reversed conductor tempos rejected by installed strict CLI with exit 3. Inputs/outputs retained under 中文 MIDI fixtures/.
- Existing full-suite checks cover stale approval hashes and snapshot races, locked tracks, missing-meter defaults, atomic non-overwrite, partial writes, concurrent output creation, positive-duration note collapse on PPQ reduction, lane membership and trailing silence. Fault injections only in temporary directories.
- No unhandled P0/P1 found in performed audit. This is technical evidence, not Windows or Cubase acceptance.

## Historical evidence and boundaries
Historical tested SHA 94081bd55564720474565fb3c06a38fbdcb3c007 differs from starting HEAD only in docs/evidence. Historical evidence checksum list verified completely (historical-hashes.log); bootstrap JSON pins source and gate_exit 0. Historical 334/4 vs 329/9 counts and skips match reports; historical 3.12/3.13 overall status was already EXPECTED_HEAD_REQUIRED_FOR_RELEASE, not full version certification. Original wheel/ZIP hashes remain verified, not substituted with rebuilt package hashes.

review→approve uses pretty_midi and still does not preserve SysEx, some text/markers or conductor track name; disclosed existing limitation, not rewritten. Use cubase prepare on original source for its preservation contract. Unicode byte preservation does not certify Cubase display encoding.

Windows scripts statically reviewed: launcher explicitly requires Python 3.11, separate from package 3.11–3.13 support; literal path handling/argument arrays, existing destination refusal, native install/smoke/help exit checks. Failed installation deliberately leaves a partial NEW venv identified in its error; old installation is not overwritten. No Windows/pwsh available: syntax parser and native execution NOT_RUN. ZIP member hashes verified in zip-integrity.json. No Windows PASS claimed. No optional AI/model/Basic Pitch expansion.

## Commands and provenance
Actual working root: /workspace/midivolt-audit. Dependency installs used isolated venvs, logs and freeze*.txt retained. Initial sandbox socket errors were resolved using authorized loopback execution, not product fixes. Original intermediate logs are superseded. Full pytest output separately retained; official gate JSON is unmodified and the gate itself retains only stdout/stderr tails. Packages and new independent probe fixtures are committed here. Historical workflow probe automatically deletes its temporary inputs. Wheelhouse caches remain at /workspace/rc-wheelhouse, /workspace/rc-wheelhouse311, /workspace/rc-wheelhouse313.

```sh
# root /workspace/midivolt-audit
PYTHONPATH=src /workspace/rc-venv/bin/python -m pytest -q tests/test_audit_event_order.py # before: 1
PYTHONPATH=src /workspace/rc-venv/bin/python -m pytest -q tests/test_audit_event_order.py tests/test_cubase_smf.py tests/test_cubase_track_integrity.py # final: 0
/workspace/rc311/bin/python scripts/verify_pre_machine_rc.py --expected-head 12c59e329afda6818df26f9e103fb04629dc19c1 --wheelhouse /workspace/rc-wheelhouse311 # 0
/workspace/rc-venv/bin/python scripts/verify_pre_machine_rc.py --wheelhouse /workspace/rc-wheelhouse # 2, seven stages PASS
/workspace/rc313/bin/python scripts/verify_pre_machine_rc.py --wheelhouse /workspace/rc-wheelhouse313 # 2, seven stages PASS
# each interpreter: PYTHONPATH=src <python> -m pytest -q -rs; final-pytest*.exit = 0
/workspace/rc311/bin/python -m pip wheel --no-deps --no-build-isolation --wheel-dir /workspace/audit-results/artifacts .
/workspace/rc311/bin/python docs/evidence/closeout-20261102/build_windows_rc_zip.py /workspace/audit-results/artifacts/midivolt-0.1.0rc1-py3-none-any.whl . /workspace/audit-results/artifacts
/workspace/rc311/bin/python -m venv /workspace/rc-clean
/workspace/rc-clean/bin/python -m pip install --no-index --find-links /workspace/rc-wheelhouse311 /workspace/audit-results/artifacts/midivolt-0.1.0rc1-py3-none-any.whl
# cwd /tmp; unset PYTHONPATH and PYTHONHOME for each:
/workspace/rc-clean/bin/python /workspace/audit-results/independent_probe.py
/workspace/rc-clean/bin/python /workspace/midivolt-audit/docs/evidence/closeout-20261102/midi_workflow_probe.py /workspace/rc-clean/bin /workspace/audit-results/workflow.json
/workspace/rc-clean/bin/python /workspace/midivolt-audit/scripts/accept_music21_core.py
/workspace/rc-clean/bin/python -m pip check
```

## Device continuation
Verify ZIP SHA256, extract to new folder; Python 3.11 x64 and py.exe required:
```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Verify-MIDIVOLT-RC.ps1 -AllowNetwork
```
Require result JSON status PASS. Prepare approved MIDI using original PPQ, import prepared.mid into real Cubase, audition retriggers/controllers/drums/tempo and full song start/end, export Type 1 at same PPQ to returned.mid:
```powershell
midivolt-cubase prepare --input approved.mid --out prepared.mid --ppq 480
midivolt-cubase compare --reference prepared.mid --returned returned.mid --strict
```
Replace 480 with actual original PPQ. Preserve both files and classify differences; do not weaken strict comparison. Windows/Cubase/listening remain NOT_RUN.
