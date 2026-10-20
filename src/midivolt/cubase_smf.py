"""Cubase-oriented Standard MIDI File (SMF) preflight and loss-audited export.

The exporter uses mido's event representation rather than pretty_midi's
higher-level reconstruction so CC, pitch bend, SysEx, text and marker events
survive wherever the SMF supports them. Cubase itself is not automated here.
"""
from __future__ import annotations

from collections import Counter, defaultdict, deque
from hashlib import sha256
import json
from pathlib import Path
import os
import tempfile

import mido

GLOBAL_META = frozenset(("set_tempo", "time_signature", "key_signature"))
MIN_PPQ = 24
MAX_PPQ = 960


def _read(path: str | Path) -> mido.MidiFile:
    source = Path(path)
    if source.suffix.lower() not in (".mid", ".midi"):
        raise ValueError("Standard MIDI file must end with .mid or .midi")
    if not source.is_file():
        raise FileNotFoundError(source)
    midi = mido.MidiFile(str(source))
    if midi.type not in (0, 1):
        raise ValueError("SMF type 2 is not supported by the Cubase interchange profile")
    if midi.ticks_per_beat <= 0:
        raise ValueError("SMF must have positive PPQ")
    return midi


def _events(track: mido.MidiTrack):
    absolute = 0
    for msg in track:
        absolute += msg.time
        if msg.type != "end_of_track":
            yield absolute, msg


def _scale(tick: int, src_ppq: int, dst_ppq: int) -> int:
    # All SMF ticks are nonnegative; round half up for deterministic MIDI timing.
    return (tick * dst_ppq * 2 + src_ppq) // (2 * src_ppq)


def _signature(midi: mido.MidiFile, dest_ppq: int) -> Counter:
    events = Counter()
    for track in midi.tracks:
        for tick, msg in _events(track):
            item = msg.dict()
            item.pop("time", None)
            events[(_scale(tick, midi.ticks_per_beat, dest_ppq),
                    json.dumps(item, sort_keys=True, ensure_ascii=False))] += 1
    return events


def _count_note_ons(midi: mido.MidiFile) -> int:
    return sum(
        1 for track in midi.tracks for msg in track
        if msg.type == "note_on" and msg.velocity > 0
    )


def _check_short_notes(midi: mido.MidiFile, dst_ppq: int):
    """Reject resolutions that collapse positive-duration notes into zero ticks."""
    for track in midi.tracks:
        starts = defaultdict(deque)
        for tick, msg in _events(track):
            if msg.type == "note_on" and msg.velocity > 0:
                starts[(msg.channel, msg.note)].append(tick)
            elif msg.type == "note_off" or (
                msg.type == "note_on" and msg.velocity == 0
            ):
                q = starts[(msg.channel, msg.note)]
                if q:
                    started = q.popleft()
                    if tick > started and _scale(tick, midi.ticks_per_beat, dst_ppq) <= (
                        _scale(started, midi.ticks_per_beat, dst_ppq)
                    ):
                        raise ValueError(
                            "PPQ conversion would collapse a positive-duration note; "
                            "choose a higher --ppq or preserve original timing"
                        )


def inspect_smf(path: str | Path) -> dict:
    midi = _read(path)
    counts = Counter(msg.type for track in midi.tracks for msg in track)
    misplaced = sum(
        1 for track in midi.tracks[1:] for msg in track
        if msg.is_meta and msg.type in GLOBAL_META
    )
    warnings = []
    if midi.type == 0:
        warnings.append("Type 0 combines all MIDI channels; export can split channels into Type 1.")
    if misplaced:
        warnings.append(
            f"{misplaced} global tempo/meter/key events are outside track 0; "
            "Cubase Type 1 export will relocate them to the conductor track."
        )
    if midi.ticks_per_beat > MAX_PPQ:
        warnings.append(
            f"Original PPQ {midi.ticks_per_beat} exceeds the optional "
            "24..960 export profile; conversion can quantize fine timing."
        )
    if counts["sysex"]:
        warnings.append("SysEx data is preserved in the SMF, but hardware/plugin behavior is not guaranteed.")
    if midi.type == 1 and len(midi.tracks) == 1:
        warnings.append("Type 1 has one track; Cubase multitrack arrangement not present.")
    return {
        "input": str(Path(path).resolve()),
        "sha256": sha256(Path(path).read_bytes()).hexdigest(),
        "type": midi.type,
        "ppq": midi.ticks_per_beat,
        "tracks": len(midi.tracks),
        "notes_on": _count_note_ons(midi),
        "tempo_events": counts["set_tempo"],
        "meter_events": counts["time_signature"],
        "key_events": counts["key_signature"],
        "control_changes": counts["control_change"],
        "pitch_bends": counts["pitchwheel"],
        "sysex_events": counts["sysex"],
        "nonconductor_global_meta": misplaced,
        "warnings": warnings,
    }


def _pack(events: list[tuple[int, mido.Message]], end_tick: int) -> mido.MidiTrack:
    track = mido.MidiTrack()
    before = 0
    for absolute, message in sorted(events, key=lambda x: x[0]):
        if absolute < before:
            raise ValueError("Negative event delta after normalization")
        track.append(message.copy(time=absolute - before))
        before = absolute
    track.append(mido.MetaMessage("end_of_track", time=max(0, end_tick - before)))
    return track


def _make_type1(midi: mido.MidiFile, ppq: int) -> mido.MidiFile:
    conductor: list[tuple[int, mido.Message]] = []
    tracks: list[list[tuple[int, mido.Message]]] = []
    ends: list[int] = []
    if midi.type == 0:
        per_channel: dict[int, list[tuple[int, mido.Message]]] = {}
        channel_ends = {}
        total_tick = 0
        for tick, msg in _events(midi.tracks[0]):
            new_tick = _scale(tick, midi.ticks_per_beat, ppq)
            total_tick = max(total_tick, new_tick)
            if hasattr(msg, "channel"):
                per_channel.setdefault(msg.channel, []).append((new_tick, msg))
                channel_ends[msg.channel] = new_tick
            else:
                conductor.append((new_tick, msg))
        for channel in sorted(per_channel):
            tracks.append(per_channel[channel])
            ends.append(channel_ends[channel])
        conductor_end = total_tick
    else:
        conductor_end = 0
        for index, original in enumerate(midi.tracks):
            musical: list[tuple[int, mido.Message]] = []
            end = 0
            for tick, msg in _events(original):
                new_tick = _scale(tick, midi.ticks_per_beat, ppq)
                end = max(end, new_tick)
                if msg.is_meta and msg.type in GLOBAL_META:
                    conductor.append((new_tick, msg))
                    conductor_end = max(conductor_end, new_tick)
                elif index == 0 and msg.is_meta:
                    conductor.append((new_tick, msg))
                    conductor_end = max(conductor_end, new_tick)
                else:
                    musical.append((new_tick, msg))
            if musical:
                tracks.append(musical)
                ends.append(end)
    out = mido.MidiFile(type=1, ticks_per_beat=ppq)
    out.tracks.append(_pack(conductor, conductor_end))
    for events, end in zip(tracks, ends):
        out.tracks.append(_pack(events, end))
    return out


def prepare_smf(source: str | Path, destination: str | Path, *,
                ppq: int = 480) -> dict:
    """Export Type 1 conductor+multitrack SMF, never replacing source/existing files."""
    src = Path(source).expanduser().resolve()
    target = Path(destination).expanduser().resolve()
    if src == target:
        raise ValueError("Source and destination must differ")
    if not isinstance(ppq, int) or isinstance(ppq, bool) or not MIN_PPQ <= ppq <= MAX_PPQ:
        raise ValueError("Export PPQ must be 24..960")
    if target.suffix.lower() not in (".mid", ".midi") or not target.parent.is_dir():
        raise ValueError("Output must be .mid/.midi in an existing directory")
    if target.exists():
        raise FileExistsError(f"Refusing to overwrite {target}")
    midi = _read(src)
    _check_short_notes(midi, ppq)
    prepared = _make_type1(midi, ppq)
    if _signature(midi, ppq) != _signature(prepared, ppq):
        raise ValueError("Export changed one or more MIDI event values or tick positions")
    fd, staging = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    os.close(fd)
    staged = Path(staging)
    try:
        prepared.save(str(staged))
        reopened = _read_mido_temp(staged)
        if _signature(midi, ppq) != _signature(reopened, ppq):
            raise ValueError("Serialized SMF roundtrip changed MIDI event content")
        try:
            os.link(staged, target)
        except FileExistsError as exc:
            raise FileExistsError(f"Refusing to overwrite {target}") from exc
    finally:
        staged.unlink(missing_ok=True)
    return {
        "source": str(src),
        "output": str(target),
        "type": 1,
        "ppq_original": midi.ticks_per_beat,
        "ppq_export": ppq,
        "tracks": len(prepared.tracks),
        "note_events": _count_note_ons(prepared),
        "all_midi_events_preserved_after_tick_rescale": True,
        "source_sha256": sha256(src.read_bytes()).hexdigest(),
        "output_sha256": sha256(target.read_bytes()).hexdigest(),
        "timing_quantization_possible": midi.ticks_per_beat != ppq,
        "cubase_application_import_verified": False,
    }


def _read_mido_temp(path: Path) -> mido.MidiFile:
    return mido.MidiFile(str(path))


def compare_smf(reference: str | Path, returned: str | Path) -> dict:
    """Compare Cubase-exported result semantically, in original PPQ units."""
    before = _read(reference)
    after = _read(returned)
    # Canonical common PPQ is the product (not rounded fraction) so events
    # with differing PPQ have an exact tick-position comparison.
    common_ppq = before.ticks_per_beat * after.ticks_per_beat
    events_before = _signature(before, common_ppq)
    events_after = _signature(after, common_ppq)
    missing = events_before - events_after
    added = events_after - events_before
    return {
        "source": str(Path(reference).resolve()),
        "roundtrip": str(Path(returned).resolve()),
        "reference_tracks": len(before.tracks),
        "returned_tracks": len(after.tracks),
        "note_on_reference": _count_note_ons(before),
        "note_on_returned": _count_note_ons(after),
        "exact_event_match": not missing and not added,
        "missing_events": sum(missing.values()),
        "added_events": sum(added.values()),
        "warning": (
            "Strict comparison includes metadata, track names, program/CC and "
            "tempo events. Cubase may intentionally transform them based on import "
            "options; inspect its preferences and exported file."
        ),
        "cubase_import_verified": False,
    }
