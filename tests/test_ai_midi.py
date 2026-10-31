"""Real provider-protocol integration, untrusted note safety, review and SMF.

No live paid provider account is assumed. Tests do send actual HTTP to
a fake LOOPBACK Ollama server, and prove its response becomes real MIDI.
"""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import os
from pathlib import Path
import threading

import pretty_midi
import pytest

from midivolt.ai_midi import (
    AIProviderError, DEFAULT_ENDPOINTS, validated_endpoint,
    request_notes, generated_to_midi, model_instructions, source_context,
)
from midivolt.ai_cli import parser, execute, main
from midivolt.io import read_midi, write_midi
from midivolt.prompt_music import parse_prompt
from midivolt.review_engine import check_proposal, apply_proposal


def response_docs():
    return {
        "tracks": [
            {"role": "melody", "notes": [
                {"pitch": 62, "start_beat": 0, "duration_beats": 1,
                 "velocity": 94},
                {"pitch": 65, "start_beat": 1.5, "duration_beats": .5,
                 "velocity": 77},
            ]},
            {"role": "bass", "notes": [
                {"pitch": 38, "start_beat": 0, "duration_beats": 2,
                 "velocity": 87},
            ]},
        ]
    }


class FakeResponse:
    def __init__(self, data):
        self.data = io.BytesIO(json.dumps(data).encode())
    def __enter__(self):
        return self
    def __exit__(self, *_):
        self.data.close()
    def read(self, n=-1):
        return self.data.read(n)


def scripted_transport(document=None, provider="ollama", spy=None):
    doc = response_docs() if document is None else document
    outer = ({
        "choices": [{"finish_reason": "stop", "message": {
            "content": json.dumps(doc)}}]}
        if provider == "openai" else
        {"done": True, "message": {"content": json.dumps(doc)}}
    )
    def post(request, timeout):
        if spy is not None:
            spy.append({
                "url": request.full_url,
                "body": json.loads(request.data),
                "authorization": request.get_header("Authorization"),
                "timeout": timeout,
            })
        return FakeResponse(outer)
    return post


def argv(tmp_path, **changes):
    params = [
        "--provider", "ollama", "--model", "my-local-music-model",
        "--prompt", "2 bars of melody and bass in D minor at 100 BPM",
        "--out", str(tmp_path / "output.mid"), "--allow-network",
    ]
    if changes.get("input_file"):
        params += ["--input", str(changes["input_file"]),
                   "--manifest", str(tmp_path / "proposal.json")]
    return parser().parse_args(params)


def midi_source(path):
    m = pretty_midi.PrettyMIDI(initial_tempo=100)
    t = pretty_midi.Instrument(program=73, name="Original flute")
    t.notes.append(pretty_midi.Note(velocity=83, pitch=67, start=0, end=3))
    t.control_changes.append(pretty_midi.ControlChange(1, 35, .5))
    m.instruments.append(t)
    write_midi(m, path)
    return m


def test_schema_produces_two_independent_tracks_and_real_serializable_midi(tmp_path):
    request = argv(tmp_path)
    spy = []
    report = execute(request, transport=scripted_transport(spy=spy))
    assert report["mode"] == "actual_AI_service_response"
    assert not report["generated_by_rules"]
    assert not report["independent_musical_quality_verified"]
    assert not report["approval_required"]
    assert len(spy) == 1
    assert spy[0]["url"] == DEFAULT_ENDPOINTS["ollama"]
    assert spy[0]["body"]["format"] == "json"
    assert [t.name for t in read_midi(tmp_path/"output.mid").instruments] == [
        "MIDIVOLT AI | Melody", "MIDIVOLT AI | Bass",
    ]
    assert report["generated_notes"] == 3


def test_non_destructive_existing_midi_requires_separate_review_approval(tmp_path):
    original = tmp_path / "source.mid"
    midi_source(original)
    before = original.read_bytes()
    req = argv(tmp_path, input_file=original)
    report = execute(req, transport=scripted_transport())
    assert report["approval_required"]
    assert original.read_bytes() == before
    assert report["locked_source_tracks"] == [0]
    proposal, diff = check_proposal(tmp_path/"proposal.json")
    assert diff["notes_added"] == 3
    assert diff["notes_removed"] == 0
    candidate = read_midi(tmp_path/"output.mid")
    assert len(candidate.instruments) == 3
    assert candidate.instruments[0].control_changes[0].value == 35
    assert min(n.start for n in candidate.instruments[1].notes) == pytest.approx(4.8, abs=.002)
    with pytest.raises(PermissionError):
        apply_proposal(tmp_path/"proposal.json", tmp_path/"approved.mid", approved=False)
    applied = apply_proposal(tmp_path/"proposal.json", tmp_path/"approved.mid", approved=True)
    assert applied["approved"] is True
    assert len(read_midi(tmp_path/"approved.mid").instruments) == 3


def test_ai_extension_rejects_source_mutated_during_provider_call(tmp_path):
    original = tmp_path / "source.mid"
    midi_source(original)
    original_bytes = original.read_bytes()
    req = argv(tmp_path, input_file=original)
    observed = []
    provider = scripted_transport(spy=observed)

    def concurrent_editor(request, timeout):
        edited = read_midi(original)
        edited.instruments[0].notes[0].pitch = 71
        write_midi(edited, original, overwrite=True)
        return provider(request, timeout)

    with pytest.raises(ValueError, match="Source MIDI changed during AI inference"):
        execute(req, transport=concurrent_editor)
    assert len(observed) == 1  # No real provider: fixture HTTP response only.
    assert original.read_bytes() != original_bytes
    assert not (tmp_path / "output.mid").exists()
    assert not (tmp_path / "proposal.json").exists()


def test_ai_extension_rejects_source_mutated_while_being_parsed(tmp_path, monkeypatch):
    import midivolt.ai_cli as ai_cli

    original = tmp_path / "source.mid"
    midi_source(original)
    req = argv(tmp_path, input_file=original)
    read_original = ai_cli.read_midi
    observed = []

    def editing_read(path):
        snapshot = read_original(path)
        edited = read_original(path)
        edited.instruments[0].notes[0].pitch = 72
        write_midi(edited, original, overwrite=True)
        return snapshot

    monkeypatch.setattr(ai_cli, "read_midi", editing_read)
    with pytest.raises(ValueError, match="Source MIDI changed while it was being read"):
        execute(req, transport=scripted_transport(spy=observed))
    assert not observed  # Cancel before a billable AI request.
    assert not (tmp_path / "output.mid").exists()
    assert not (tmp_path / "proposal.json").exists()


def test_no_user_network_consent_fails_before_transport(tmp_path):
    req = argv(tmp_path)
    req.allow_network = False
    called = []
    with pytest.raises(PermissionError, match="--allow-network"):
        execute(req, transport=scripted_transport(spy=called))
    assert not called
    assert not (tmp_path/"output.mid").exists()


def test_openai_key_is_from_environment_not_request_body(tmp_path, monkeypatch):
    monkeypatch.setenv("MIDIVOLT_OPENAI_API_KEY", "secret-unit-test-key")
    spec = parse_prompt("melody and bass in D minor", bars=2, bpm=100)
    sent = []
    document = request_notes(
        "openai", "test-chat-model", spec, allow_network=True,
        transport=scripted_transport(provider="openai", spy=sent),
    )
    assert document == response_docs()
    assert sent[0]["authorization"] == "Bearer secret-unit-test-key"
    assert "secret-unit-test-key" not in json.dumps(sent[0]["body"])
    assert sent[0]["body"]["response_format"]["type"] == "json_object"


def test_missing_cloud_credential_cannot_call_transport(monkeypatch):
    monkeypatch.delenv("MIDIVOLT_OPENAI_API_KEY", raising=False)
    spy = []
    with pytest.raises(PermissionError, match="MIDIVOLT_OPENAI_API_KEY"):
        request_notes(
            "openai", "test", parse_prompt("melody"),
            allow_network=True,
            transport=scripted_transport(provider="openai", spy=spy),
        )
    assert not spy


@pytest.mark.parametrize("endpoint", [
    "http://example.com/v1/chat/completions",
    "https://user:password@example.com/v1/chat/completions",
    "file:///etc/passwd",
    "https://evil.example/api#fragment",
    "https://evil.example/api?token=secret",
])
def test_dangerous_endpoints_rejected(endpoint):
    with pytest.raises(ValueError):
        validated_endpoint("openai", endpoint)


def test_custom_https_cloud_endpoint_needs_additional_explicit_consent():
    url = "https://llm.example.com/v1/chat/completions"
    with pytest.raises(ValueError, match="--allow-remote-endpoint"):
        validated_endpoint("openai", url)
    assert validated_endpoint("openai", url, allow_remote_endpoint=True) == url


def test_model_output_cannot_change_missing_or_duplicate_roles():
    spec = parse_prompt("melody bass", bars=2)
    doc = response_docs()
    bad = {"tracks": [doc["tracks"][0], doc["tracks"][0]]}
    with pytest.raises(ValueError, match="duplicate"):
        generated_to_midi(bad, spec)
    with pytest.raises(ValueError, match="track count"):
        generated_to_midi({"tracks": [doc["tracks"][0]]}, spec)


@pytest.mark.parametrize("field,value", [
    ("pitch", -1), ("pitch", True),
    ("velocity", 0), ("velocity", 128),
    ("start_beat", -2), ("duration_beats", 0),
    ("duration_beats", float("nan")),
    ("start_beat", 10), ("duration_beats", 9),
])
def test_invalid_note_bounds_rejected(field, value):
    doc = response_docs()
    doc["tracks"][0]["notes"][0][field] = value
    with pytest.raises(ValueError):
        generated_to_midi(doc, parse_prompt("2 bars melody bass"))


def test_unrecognized_fields_and_code_like_responses_rejected():
    doc = response_docs()
    doc["tracks"][0]["notes"][0]["exec"] = "__import__('os').system('whoami')"
    with pytest.raises(ValueError, match="missing/extra"):
        generated_to_midi(doc, parse_prompt("2 bars melody bass"))
    with pytest.raises(ValueError, match="exactly tracks"):
        generated_to_midi({"tracks": [], "python": "something"}, parse_prompt("melody"))


def test_require_general_midi_percussion_mapping():
    spec = parse_prompt("drums", bars=2)
    bad = {"tracks": [{"role": "drums", "notes": [
        {"pitch": 25, "start_beat": 0, "duration_beats": 1, "velocity": 90},
    ]}]}
    with pytest.raises(ValueError, match="General MIDI"):
        generated_to_midi(bad, spec)


def test_failing_provider_or_invalid_output_never_publishes_destination(tmp_path):
    req = argv(tmp_path)
    def failed(request, timeout):
        return FakeResponse({"done": True, "message": {"content": "not valid JSON"}})
    with pytest.raises(AIProviderError, match="valid JSON"):
        execute(req, transport=failed)
    assert not (tmp_path/"output.mid").exists()


def test_original_midi_context_is_bounded_and_explicit(tmp_path):
    path = tmp_path / "source.mid"
    midi_source(path)
    context = source_context(read_midi(path), parse_prompt("melody", bpm=100))
    assert len(context["tracks"]) == 1
    assert context["tracks"][0]["notes"][0]["pitch"] == 67
    assert "source_excerpt" in model_instructions(parse_prompt("melody", bpm=100), read_midi(path))[1]["content"]


def test_consent_with_actual_loopback_http_server(tmp_path):
    """Real HTTP request and response over TCP; server is a fake provider."""
    observed = []
    class Stub(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("Content-Length", "0"))
            observed.append(json.loads(self.rfile.read(length)))
            body = json.dumps({
                "done": True,
                "message": {"content": json.dumps(response_docs())}
            }).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        def log_message(self, *args):
            return
    server = ThreadingHTTPServer(("127.0.0.1", 0), Stub)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        req = argv(tmp_path)
        req.endpoint = f"http://127.0.0.1:{server.server_port}/api/chat"
        result = execute(req)
        assert result["mode"] == "actual_AI_service_response"
        assert (tmp_path/"output.mid").is_file()
        assert observed[0]["model"] == "my-local-music-model"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
