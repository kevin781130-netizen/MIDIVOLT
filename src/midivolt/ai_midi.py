"""Opt-in real LLM text-to-MIDI provider and strict event validation.

Supports OpenAI Chat Completions over TLS and a local Ollama daemon.
No network request without explicit consent; NO fallback masquerading
as AI. Provider output is untrusted JSON, NEVER executed as Python.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import ipaddress
import urllib.error
import urllib.parse
import urllib.request

import pretty_midi

from .prompt_music import PromptSpec, PARTS

SCHEMA = "midivolt.ai_midi.v1"
MAX_RESPONSE_BYTES = 256_000
MAX_SOURCE_CONTEXT_NOTES = 160
MAX_NOTES_PER_TRACK = 1024
GM_PROGRAMS = {"chords": 0, "melody": 80, "bass": 33, "drums": 0}
DEFAULT_ENDPOINTS = {
    "openai": "https://api.openai.com/v1/chat/completions",
    "ollama": "http://127.0.0.1:11434/api/chat",
}


class AIProviderError(RuntimeError):
    """Inference/refusal/protocol failure; does not return fallback MIDI."""


def _finite_number(value, *, name, minimum, maximum):
    if type(value) not in (float, int) or not math.isfinite(value) or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be finite and within {minimum}..{maximum}")
    return float(value)


def _is_loopback(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def validated_endpoint(provider: str, endpoint: str, *, allow_remote_endpoint=False) -> str:
    if provider not in DEFAULT_ENDPOINTS:
        raise ValueError("Unsupported AI provider: use openai or ollama")
    if not isinstance(endpoint, str) or len(endpoint) > 2048:
        raise ValueError("Invalid provider endpoint")
    u = urllib.parse.urlsplit(endpoint)
    if (u.username is not None or u.password is not None or u.fragment
            or not u.hostname or not u.path or u.scheme not in ("http", "https")
            or u.query or not u.netloc):
        raise ValueError("Endpoint must be an unambiguous HTTP(S) URL without credentials")
    if u.port is not None and not 1 <= u.port <= 65535:
        raise ValueError("Invalid provider port")
    if u.scheme == "http" and not _is_loopback(u.hostname):
        raise ValueError("Plain HTTP is allowed only on a local loopback endpoint")
    if not _is_loopback(u.hostname):
        if u.scheme != "https":
            raise ValueError("Cloud providers must use TLS")
        if endpoint != DEFAULT_ENDPOINTS["openai"] and not allow_remote_endpoint:
            raise ValueError("Custom remote AI endpoints require --allow-remote-endpoint")
    if provider == "openai" and endpoint == DEFAULT_ENDPOINTS["ollama"]:
        raise ValueError("Use provider ollama for the native Ollama endpoint")
    return endpoint


def source_context(midi: pretty_midi.PrettyMIDI | None, spec: PromptSpec) -> dict | None:
    if midi is None:
        return None
    if not isinstance(midi, pretty_midi.PrettyMIDI):
        raise ValueError("Existing context must be a MIDI file")
    if any((x.numerator, x.denominator) != (4, 4) for x in midi.time_signature_changes):
        raise ValueError("AI extension currently supports 4/4 MIDI only")
    _, tempo = midi.get_tempo_changes()
    if len(tempo) != 1 or abs(float(tempo[0])-spec.bpm) > 0.02:
        raise ValueError("Existing MIDI must have constant matching tempo")
    seconds_per_beat = 60.0/spec.bpm
    tracks = []
    total = 0
    for track in midi.instruments:
        events = sorted(track.notes, key=lambda n: (n.start, n.pitch))
        if total + len(events) > MAX_SOURCE_CONTEXT_NOTES:
            raise ValueError("Existing MIDI has too many notes for bounded AI context")
        total += len(events)
        tracks.append({
            "name": str(track.name)[:80],
            "program": int(track.program), "is_drum": bool(track.is_drum),
            "notes": [{
                "pitch": int(n.pitch),
                "start_beat": round(n.start/seconds_per_beat, 5),
                "duration_beats": round((n.end-n.start)/seconds_per_beat, 5),
                "velocity": int(n.velocity),
            } for n in events],
        })
    return {"tracks": tracks, "source_duration_beats": round(midi.get_end_time()/seconds_per_beat, 5)}


def model_instructions(spec: PromptSpec, source: pretty_midi.PrettyMIDI | None = None) -> list[dict]:
    original = source_context(source, spec)
    contract = {
        "schema": SCHEMA,
        "key": spec.key, "mode": spec.mode, "bars": spec.bars,
        "tempo_bpm": spec.bpm, "required_roles": list(spec.parts),
        "total_beats": spec.bars*4, "seed": spec.seed,
        "source_excerpt": original,
        "output_contract": {
            "tracks": [{
                "role": "melody",
                "notes": [{"pitch": 60, "start_beat": 0.0, "duration_beats": 1.0, "velocity": 90}],
            }],
        },
    }
    system = (
        "Compose ORIGINAL editable Standard MIDI note events as a single JSON object. "
        "Use exactly one track per required role; roles limited to chords, melody, bass, drums. "
        "The output must contain only a 'tracks' array, with each track containing 'role' and "
        "'notes', and each note containing pitch (integer 0..127), start_beat (number), "
        "duration_beats (positive number), velocity (integer 1..127). "
        "Starts are RELATIVE to the requested new bars, in 4/4 quarter-note beats. "
        "Every role must contain notes. Do not copy referenced songs or recognizable melodies. "
        "If source_excerpt exists, use only as inspiration for an extension, do not return "
        "or alter original notes. Drums must use standard GM drum pitches 35..81. "
        "Do not include code, explanations, markdown, timing maps, or metadata. "
        "Your response MUST be valid JSON."
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps({
            "musical_direction": spec.prompt,
            "constraints": contract,
        }, ensure_ascii=False, separators=(",", ":"))},
    ]


def _decode_response(provider: str, response: dict) -> str:
    try:
        if provider == "openai":
            choice = response["choices"][0]
            if choice.get("finish_reason") not in (None, "stop"):
                raise AIProviderError("AI provider response was incomplete or filtered")
            msg = choice["message"]
            if msg.get("refusal"):
                raise AIProviderError("AI provider refused this generation")
            content = msg["content"]
        else:
            if response.get("done") is False:
                raise AIProviderError("Local AI response was not complete")
            content = response["message"]["content"]
        if not isinstance(content, str) or not content.strip():
            raise AIProviderError("AI provider returned no text content")
        return content
    except (KeyError, TypeError, IndexError) as exc:
        raise AIProviderError("AI provider response is missing the expected message") from exc


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        raise AIProviderError("Refusing AI provider redirect; credentials may not be forwarded")


def request_notes(
    provider: str, model: str, spec: PromptSpec,
    *, endpoint: str | None = None, api_key_env: str = "MIDIVOLT_OPENAI_API_KEY",
    allow_network: bool = False, allow_remote_endpoint: bool = False,
    source: pretty_midi.PrettyMIDI | None = None,
    timeout: float = 35.0, transport=None,
) -> dict:
    if not allow_network:
        raise PermissionError("AI network inference requires explicit --allow-network")
    if not isinstance(model, str) or not 1 <= len(model) <= 128 or any(ord(c) < 32 for c in model):
        raise ValueError("Model identifier must contain 1..128 printable characters")
    _finite_number(timeout, name="timeout", minimum=1, maximum=120)
    url = validated_endpoint(
        provider, endpoint or DEFAULT_ENDPOINTS.get(provider, ""),
        allow_remote_endpoint=allow_remote_endpoint,
    )
    if provider == "openai":
        if not isinstance(api_key_env, str) or not api_key_env.isidentifier():
            raise ValueError("API key variable must be a valid environment name")
        key = os.environ.get(api_key_env, "")
        if not key:
            raise PermissionError(f"OpenAI-compatible provider requires {api_key_env} environment variable")
        if "\r" in key or "\n" in key:
            raise ValueError("Invalid credential characters")
    else:
        key = None
    messages = model_instructions(spec, source=source)
    if provider == "openai":
        payload = {
            "model": model, "messages": messages,
            "response_format": {"type": "json_object"},
        }
    else:
        payload = {"model": model, "messages": messages,
                   "format": "json", "stream": False,
                   "options": {"temperature": 0.4, "seed": spec.seed}}
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    if len(body) > MAX_RESPONSE_BYTES:
        raise ValueError("AI request too large")
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if key:
        headers["Authorization"] = "Bearer " + key
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    if transport is None:
        transport = urllib.request.build_opener(_NoRedirect()).open
    try:
        with transport(request, timeout=timeout) as response:
            # Response is always bounded. Never log raw provider payload.
            raw = response.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES:
                raise AIProviderError("AI provider response exceeds maximum JSON size")
            outer = json.loads(raw)
        content = _decode_response(provider, outer)
        if len(content.encode("utf-8")) > MAX_RESPONSE_BYTES:
            raise AIProviderError("Model-generated MIDI JSON exceeds maximum size")
        document = json.loads(content)
        if not isinstance(document, dict):
            raise ValueError("AI model must return a JSON object")
        return document
    except urllib.error.HTTPError as exc:
        raise AIProviderError(f"AI provider returned HTTP {exc.code}") from None
    except (urllib.error.URLError, TimeoutError) as exc:
        raise AIProviderError("AI provider is unreachable or timed out") from None
    except json.JSONDecodeError as exc:
        raise AIProviderError("AI provider did not return valid JSON") from None


def generated_to_midi(
    document: dict, spec: PromptSpec, *,
    source: pretty_midi.PrettyMIDI | None = None,
) -> pretty_midi.PrettyMIDI:
    """Fail closed for untrusted LLM events; never modify source tracks."""
    if not isinstance(document, dict) or set(document) != {"tracks"}:
        raise ValueError("AI document must contain exactly tracks")
    supplied = document["tracks"]
    if not isinstance(supplied, list) or len(supplied) != len(spec.parts):
        raise ValueError("AI must return exactly the requested track count")
    if source is None:
        base = pretty_midi.PrettyMIDI(initial_tempo=spec.bpm)
        bar_start_seconds = 0.0
    else:
        source_context(source, spec)
        base = deepcopy(source)
        bar_duration = 240.0/spec.bpm
        bar_start_seconds = max(
            0, math.ceil((base.get_end_time()-1e-8)/bar_duration)
        ) * bar_duration
    seconds_per_beat = 60.0/spec.bpm
    roles_seen = set()
    for track in supplied:
        if not isinstance(track, dict) or set(track) != {"role", "notes"}:
            raise ValueError("Each AI track must contain exactly role and notes")
        role = track["role"]
        if not isinstance(role, str) or role not in spec.parts or role in roles_seen:
            raise ValueError("Unexpected or duplicate generated instrument role")
        roles_seen.add(role)
        notes = track["notes"]
        if not isinstance(notes, list) or not 1 <= len(notes) <= MAX_NOTES_PER_TRACK:
            raise ValueError("Generated track must have 1..1024 note events")
        inst = pretty_midi.Instrument(
            program=GM_PROGRAMS[role], is_drum=(role == "drums"),
            name=f"MIDIVOLT AI | {role.capitalize()}",
        )
        for note in notes:
            if not isinstance(note, dict) or set(note) != {
                "pitch", "start_beat", "duration_beats", "velocity"
            }:
                raise ValueError("Untrusted note has missing/extra fields")
            pitch, velocity = note["pitch"], note["velocity"]
            if type(pitch) is not int or not 0 <= pitch <= 127:
                raise ValueError("Generated MIDI pitch outside range")
            if role == "drums" and not 35 <= pitch <= 81:
                raise ValueError("Drum output must use General MIDI drum pitches")
            if type(velocity) is not int or not 1 <= velocity <= 127:
                raise ValueError("Generated note velocity outside range")
            start = _finite_number(note["start_beat"], name="start_beat",
                                   minimum=0, maximum=spec.bars*4)
            duration = _finite_number(note["duration_beats"], name="duration_beats",
                                      minimum=.01, maximum=spec.bars*4)
            if start >= spec.bars*4 or start+duration > spec.bars*4 + 1e-7:
                raise ValueError("Generated note exceeds requested number of bars")
            begin = bar_start_seconds + start*seconds_per_beat
            end = begin + duration*seconds_per_beat
            inst.notes.append(pretty_midi.Note(
                pitch=pitch, velocity=velocity, start=begin, end=end,
            ))
        base.instruments.append(inst)
    if roles_seen != set(spec.parts):
        raise ValueError("AI returned a different set of instrument roles")
    return base


def inference_report(
    *, provider: str, model: str, spec: PromptSpec,
    source: pretty_midi.PrettyMIDI | None,
    generated: pretty_midi.PrettyMIDI,
    raw_document: dict,
) -> dict:
    return {
        "mode": "actual_AI_service_response",
        "provider": provider, "model": model,
        "generated_by_rules": False,
        "llm_request_sent": True,
        "provider_response_structurally_valid": True,
        "independent_musical_quality_verified": False,
        "DAW_plugin_verified": False,
        "schema": SCHEMA,
        "prompt_sha256": sha256(spec.prompt.encode("utf-8")).hexdigest(),
        "response_document_sha256": sha256(json.dumps(
            raw_document, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")).hexdigest(),
        "source_original_midi_preserved": source is not None,
        "generated_roles": list(spec.parts),
        "generated_notes": sum(len(t.notes) for t in generated.instruments[(len(source.instruments) if source else 0):]),
    }
