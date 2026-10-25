"""Leakage-resistant GM42 development examples from actual TRAIN WAV/MIDI.

Use EXACTLY the same raw subband detector as inference. Reference GM42
notes already explained by the production baseline are removed FIRST,
then remaining truth events are matched one-to-one to new candidates.
Avoid labeling a duplicate of an already-found hat as a true new hit.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
from scipy import signal

from midivolt.drums import (
    transcribe_drum_wav, read_audio, TARGET_SR, FFT_SIZE, HOP,
)
from midivolt.hat_subband import HatSubbandConfig
from midivolt.hat_candidate_confidence import (
    HatCandidateConfidence, evaluate_candidate_confidence,
)
from midivolt.evaluate import Event, matching


def _notes(midi, pitch: int = 42) -> list[Event]:
    return sorted([
        Event(n.pitch, float(n.start), float(n.end))
        for inst in midi.instruments if inst.is_drum
        for n in inst.notes if n.pitch == pitch
    ], key=lambda e: (e.start, e.end))


def label_new_candidates(
    truth, baseline, proposed, *, onset_tolerance: float = 0.05
) -> list[dict]:
    """One-to-one matches for candidate events UNEXPLAINED by baseline."""
    if not 0 < onset_tolerance <= 0.05:
        raise ValueError("Training requires frozen onset tolerance <=50ms")
    true = _notes(truth)
    old = _notes(baseline)
    raw = _notes(proposed)
    all_old = {(n.pitch, round(n.start, 7), round(n.end, 7)) for n in old}
    all_raw = {(n.pitch, round(n.start, 7), round(n.end, 7)) for n in raw}
    if not all_old.issubset(all_raw):
        raise ValueError("Proposed MIDI removed existing baseline GM42 notes")
    # Important ordering: remove baseline-matched TRUE hits first, then
    # match NEW candidate notes to still-unmatched reference events.
    original_pairs = matching(true, old, onset_tolerance, require_offset=False)
    covered_truth = {i for i, _ in original_pairs}
    unmatched_truth = [event for i, event in enumerate(true) if i not in covered_truth]
    candidates = [n for n in raw
                  if (n.pitch, round(n.start, 7), round(n.end, 7)) not in all_old]
    candidate_pairs = matching(
        unmatched_truth, candidates, onset_tolerance, require_offset=False
    )
    positives = {j for _, j in candidate_pairs}
    return [
        {"pitch": n.pitch, "onset": float(n.start),
         "label": int(i in positives)}
        for i, n in enumerate(candidates)
    ]


def source_features(wav_path: Path, truth_midi, *, source_song_id: str) -> list[dict]:
    """Extract normalized physical features, no reference used for features."""
    if not source_song_id:
        raise ValueError("Require original source_song_id")
    wav = Path(wav_path)
    baseline, _ = transcribe_drum_wav(wav)
    raw, _ = transcribe_drum_wav(wav, hat_subband_config=HatSubbandConfig())
    labels = label_new_candidates(truth_midi, baseline, raw)
    if not labels:
        return []
    audio, sr = read_audio(wav)
    if sr != TARGET_SR:
        raise RuntimeError("Unexpected STFT sample rate after standard resampling")
    hz, times, stft = signal.stft(
        audio, fs=sr, window="hann", nperseg=FFT_SIZE,
        noverlap=FFT_SIZE-HOP, boundary="zeros", padded=True,
    )
    mag = np.abs(stft)
    extracted = []
    for event in labels:
        i = int(np.argmin(np.abs(times - event["onset"])))
        measured = evaluate_candidate_confidence(
            mag, hz, i, hop_seconds=HOP/sr,
            config=HatCandidateConfidence(),
        )
        if not measured.get("features"):
            continue  # Such edges are rejected at inference as well.
        extracted.append({
            "split": "train",
            "source_song_id": source_song_id,
            "onset": event["onset"],
            "label": event["label"],
            "features": measured["features"],
        })
    return extracted


def digest_file(path: Path) -> str:
    sha = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b""):
            sha.update(chunk)
    return sha.hexdigest()


def read_train_manifest(path: Path) -> tuple[list[dict], str]:
    """No external download. TRAIN rights + source bytes must be explicit."""
    manifest = Path(path).resolve()
    raw_bytes = manifest.read_bytes()
    data = json.loads(raw_bytes)
    if (data.get("dataset") != "E-GMD v1.0.0"
            or data.get("split") != "train"
            or data.get("schema_version") != "1"):
        raise ValueError("Ranker training requires official E-GMD TRAIN manifest v1")
    songs = data.get("samples")
    if not isinstance(songs, list) or len(songs) < 4:
        raise ValueError("TRAIN dataset needs at least four original performances")
    seen = set()
    result = []
    for rec in songs:
        sid = rec.get("source_song_id")
        if rec.get("upstream_split") != "train" or not isinstance(sid, str) or not sid or sid in seen:
            raise ValueError("Non-TRAIN or duplicate original performance in TRAIN manifest")
        seen.add(sid)
        rights = rec.get("rights", {})
        if rights.get("status") != "approved" or rights.get("research_evaluation_allowed") is not True:
            raise PermissionError("TRAIN WAV/MIDI rights not approved for local development")
        if not rights.get("evidence_url") or not rights.get("audio_license") or not rights.get("midi_license"):
            raise PermissionError("TRAIN source/license evidence incomplete")
        files = []
        for path_key, sha_key, suffixes in (
            ("audio_path", "wav_sha256", (".wav",)),
            ("reference_midi_path", "midi_sha256", (".mid", ".midi")),
        ):
            rel = Path(rec.get(path_key, ""))
            if (not rec.get(path_key) or rel.is_absolute()
                    or ".." in rel.parts or rel.suffix.lower() not in suffixes):
                raise ValueError("Unsafe or unsupported TRAIN source path")
            target = (manifest.parent / rel).resolve()
            if not target.is_relative_to(manifest.parent) or not target.is_file():
                raise ValueError("TRAIN source file is missing/outside manifest folder")
            expected = rec.get(sha_key)
            if (not isinstance(expected, str) or len(expected) != 64
                    or digest_file(target) != expected):
                raise ValueError("TRAIN source SHA-256 mismatch")
            files.append(target)
        if rec.get("reference_midi_mapping") != "roland_td11_to_gm":
            raise ValueError("Official E-GMD reference MIDI mapping not declared")
        result.append({"source_song_id": sid, "wav": files[0], "midi": files[1]})
    return result, hashlib.sha256(raw_bytes).hexdigest()
