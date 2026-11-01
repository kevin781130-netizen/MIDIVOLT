"""Offline product integration: real MIDIVOLT AI CLI -> MIDI -> review -> apply.

The provider is an in-process HTTP fixture speaking Ollama's API protocol.
No pretrained model, paid network request, GPU, DAW or GitHub Actions used.
"""
from __future__ import annotations

from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from threading import Thread

import pretty_midi
import pytest

from midivolt.ai_cli import execute, parser
from midivolt.ai_midi import AIProviderError
from midivolt.io import read_midi, write_midi
from midivolt.review_engine import apply_proposal, check_proposal


def fixture_notes():
    return {"tracks": [
        {"role": "melody", "notes": [
            {"pitch": 62, "start_beat": 0, "duration_beats": 1, "velocity": 94},
            {"pitch": 65, "start_beat": 2, "duration_beats": 0.75, "velocity": 78},
        ]},
        {"role": "bass", "notes": [
            {"pitch": 38, "start_beat": 0, "duration_beats": 2, "velocity": 88},
        ]},
    ]}


@pytest.fixture
def ollama_fixture():
    state = {"requests": [], "done": True, "done_reason": "stop", "document": fixture_notes(), "on_request": None}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("Content-Length", "0"))
            request = json.loads(self.rfile.read(length))
            state["requests"].append(request)
            if state["on_request"]:
                state["on_request"]()
            body = json.dumps({
                "done": state["done"],
                "done_reason": state["done_reason"],
                "message": {"content": json.dumps(state["document"])},
            }).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield state, f"http://127.0.0.1:{server.server_port}/api/chat"
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=3)


def arguments(tmp_path: Path, endpoint: str, *, source: Path | None = None):
    values = [
        "--provider", "ollama", "--model", "fixture-only",
        "--prompt", "2 bars melody and bass in D minor at 100 BPM",
        "--endpoint", endpoint, "--allow-network", "--out", str(tmp_path / "candidate.mid"),
    ]
    if source:
        values += ["--input", str(source), "--manifest", str(tmp_path / "proposal.json")]
    return parser().parse_args(values)


def original_midi(path: Path):
    midi = pretty_midi.PrettyMIDI(initial_tempo=100)
    flute = pretty_midi.Instrument(program=73, name="Protected flute")
    flute.notes.append(pretty_midi.Note(velocity=85, pitch=65, start=0, end=3))
    flute.control_changes.append(pretty_midi.ControlChange(1, 48, 0.5))
    midi.instruments.append(flute)
    write_midi(midi, path)
    return sha256(path.read_bytes()).hexdigest()


def test_http_to_editable_multitrack_midi_without_review_for_new_song(tmp_path, ollama_fixture):
    state, url = ollama_fixture
    result = execute(arguments(tmp_path, url))
    assert result["approval_required"] is False
    midi = read_midi(tmp_path / "candidate.mid")
    assert [track.name for track in midi.instruments] == [
        "MIDIVOLT AI | Melody", "MIDIVOLT AI | Bass",
    ]
    assert midi.instruments[0].notes[0].pitch == 62
    assert midi.instruments[1].notes[0].pitch == 38
    assert len(state["requests"]) == 1
    assert state["requests"][0]["model"] == "fixture-only"
    assert not (tmp_path / "proposal.json").exists()


def test_http_to_approved_extension_preserves_original_midi(tmp_path, ollama_fixture):
    state, url = ollama_fixture
    source = tmp_path / "source.mid"
    source_sha = original_midi(source)
    result = execute(arguments(tmp_path, url, source=source))
    assert result["approval_required"] is True
    assert len(state["requests"]) == 1
    assert sha256(source.read_bytes()).hexdigest() == source_sha
    proposal, review = check_proposal(tmp_path / "proposal.json")
    assert proposal["source_sha256"] == source_sha
    assert review["locked_tracks"] == [0]
    assert review["notes_added"] == 3
    assert review["notes_removed"] == 0
    destination = tmp_path / "approved.mid"
    with pytest.raises(PermissionError):
        apply_proposal(tmp_path / "proposal.json", destination, approved=False)
    assert not destination.exists()
    approved = apply_proposal(tmp_path / "proposal.json", destination, approved=True)
    assert approved["approved"] is True
    output = read_midi(destination)
    assert [instrument.name for instrument in output.instruments] == [
        "Protected flute", "MIDIVOLT AI | Melody", "MIDIVOLT AI | Bass",
    ]
    assert output.instruments[0].control_changes[0].value == 48
    assert sha256(source.read_bytes()).hexdigest() == source_sha


def test_truncated_ollama_reply_never_creates_midi_or_manifest(tmp_path, ollama_fixture):
    state, url = ollama_fixture
    state["done_reason"] = "length"
    source = tmp_path / "source.mid"
    source_sha = original_midi(source)
    with pytest.raises(AIProviderError, match="without completion"):
        execute(arguments(tmp_path, url, source=source))
    assert len(state["requests"]) == 1
    assert sha256(source.read_bytes()).hexdigest() == source_sha
    assert not (tmp_path / "candidate.mid").exists()
    assert not (tmp_path / "proposal.json").exists()


def test_provider_wrong_track_roles_rejected_before_publish(tmp_path, ollama_fixture):
    state, url = ollama_fixture
    state["document"] = {"tracks": [fixture_notes()["tracks"][0], fixture_notes()["tracks"][0]]}
    with pytest.raises(ValueError, match="duplicate"):
        execute(arguments(tmp_path, url))
    assert not (tmp_path / "candidate.mid").exists()


def test_concurrent_source_change_during_provider_call_never_publishes(tmp_path, ollama_fixture):
    state, url = ollama_fixture
    source = tmp_path / "source.mid"
    source_sha = original_midi(source)

    def concurrent_edit():
        modified = read_midi(source)
        modified.instruments[0].notes[0].pitch = 72
        write_midi(modified, source, overwrite=True)

    state["on_request"] = concurrent_edit
    with pytest.raises(ValueError, match="Source MIDI changed during AI inference"):
        execute(arguments(tmp_path, url, source=source))
    assert sha256(source.read_bytes()).hexdigest() != source_sha
    assert not (tmp_path / "candidate.mid").exists()
    assert not (tmp_path / "proposal.json").exists()
