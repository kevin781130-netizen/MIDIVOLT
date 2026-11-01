"""Core CLI must show help without pre-importing the music21 analysis backend."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src"

# Simulate music21 missing even on a developer machine that has it installed.
BLOCK_MUSIC21 = r'''
import builtins, runpy, sys
original = builtins.__import__
def blocked(name, *args, **kwargs):
    if name == "music21" or name.startswith("music21."):
        raise ModuleNotFoundError("No module named 'music21'", name="music21")
    return original(name, *args, **kwargs)
builtins.__import__ = blocked
runpy.run_module("midivolt.cli", run_name="__main__")
'''


def cli(*args: str) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(SOURCE_ROOT)
    return subprocess.run([sys.executable, "-c", BLOCK_MUSIC21, *args],
                          capture_output=True, text=True, env=env, timeout=20)


def test_main_help_works_when_music21_is_absent():
    r = cli("--help")
    assert r.returncode == 0, r.stderr
    assert "{create,arrange,analyze,transcribe}" in r.stdout
    assert "Traceback" not in r.stderr


def test_transcribe_help_works_when_music21_is_absent():
    r = cli("transcribe", "--help")
    assert r.returncode == 0, r.stderr
    assert "--input" in r.stdout


def test_create_fails_clearly_before_output_without_music21(tmp_path):
    target = tmp_path / "missing-lib.mid"
    r = cli("create", "--chords", "Cmaj7", "--out", str(target))
    assert r.returncode == 2
    assert "music21 is required" in r.stderr
    assert "Traceback" not in r.stderr
    assert not target.exists()


def test_analyze_fails_clearly_without_music21(tmp_path):
    r = cli("analyze", "--input", str(tmp_path / "missing.mid"))
    assert r.returncode == 2
    assert "music21 is required" in r.stderr
    assert "Traceback" not in r.stderr


def test_arrange_fails_clearly_before_output_without_music21(tmp_path):
    target = tmp_path / "missing-lib.mid"
    r = cli("arrange", "--input", str(tmp_path / "input.mid"),
            "--out", str(target), "--chords", "Cmaj7")
    assert r.returncode == 2
    assert "music21 is required" in r.stderr
    assert not target.exists()
