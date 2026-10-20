"""Stand-alone DAW interchange via MIDI, without vendoring target source."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import pretty_midi

from .io import read_midi, write_midi

BridgeTarget = Literal["sawdust", "tsov"]


@dataclass(frozen=True)
class BridgeReport:
    target: str
    output: Path
    tracks: int
    notes: int
    quantized_notes: int
    warnings: tuple[str, ...]

    def as_dict(self) -> dict:
        return {
            "target": self.target, "output": str(self.output),
            "tracks": self.tracks, "notes": self.notes,
            "quantized_notes": self.quantized_notes, "warnings": list(self.warnings),
        }


def _to_sawdust_grid(midi: pretty_midi.PrettyMIDI) -> int:
    """Opt-in lossful note quantization to Sawdust's 24 steps per quarter."""
    count = 0
    resolution = midi.resolution
    for inst in midi.instruments:
        for note in inst.notes:
            start_tick = midi.time_to_tick(note.start)
            end_tick = midi.time_to_tick(note.end)
            start_step = round(start_tick * 24 / resolution)
            end_step = max(start_step + 1, round(end_tick * 24 / resolution))
            new_start = midi.tick_to_time(round(start_step * resolution / 24))
            new_end = midi.tick_to_time(round(end_step * resolution / 24))
            if new_start != note.start or new_end != note.end:
                count += 1
            note.start, note.end = new_start, new_end
    return count


def prepare_bridge(
    input_path: str | Path,
    output_path: str | Path,
    target: BridgeTarget,
    *,
    quantize: bool = False,
    overwrite: bool = False,
) -> BridgeReport:
    """Create an SMF importable by the target; never edit the input.

    This does not write Sawdust .saw or tsov native project files. These two
    applications must remain separately installed and manually import the SMF.
    """
    if target not in {"sawdust", "tsov"}:
        raise ValueError("Target must be 'sawdust' or 'tsov'.")
    src, dst = Path(input_path), Path(output_path)
    if src.resolve() == dst.resolve():
        raise ValueError("Bridge input and output must be different files.")
    if quantize and target != "sawdust":
        raise ValueError("Grid quantization is only supported for Sawdust.")

    midi = deepcopy(read_midi(src))
    notices: list[str] = []
    pitched = [inst for inst in midi.instruments if not inst.is_drum and inst.notes]
    drums = [inst for inst in midi.instruments if inst.is_drum and inst.notes]
    _, tempos = midi.get_tempo_changes()

    if len(tempos) > 1:
        notices.append("Tempo map has changes; target may use only initial tempo.")
    if len(midi.time_signature_changes) > 1:
        notices.append("Multiple time signatures may not survive target import.")

    quantized = 0
    if target == "sawdust":
        if len(pitched) > 15:
            notices.append("More than 15 pitched tracks: MIDI channels may be reused and merged.")
        if len(drums) > 1:
            notices.append("Multiple drum tracks share MIDI channel 10 and may merge.")
        if any(inst.pitch_bends for inst in midi.instruments):
            notices.append("Sawdust's MIDI import does not restore pitch bends.")
        if any(inst.control_changes for inst in midi.instruments):
            notices.append("Sawdust may discard MIDI CC automation, except initial CC10 pan.")
        if quantize:
            quantized = _to_sawdust_grid(midi)
            if quantized:
                notices.append(
                    f"Quantized {quantized} notes to Sawdust's 24-step grid (lossy)."
                )
        else:
            notices.append(
                "Sawdust imports onto a 24-step quarter-note grid; use --quantize "
                "to see this adjustment explicitly in the exported file."
            )
        notices.append(
            "Sawdust groups notes by MIDI channel; DAW track identity is not guaranteed."
        )
    else:
        if len(tempos) > 1:
            notices.append("tsov MIDI importer uses the first tempo only.")
        if len(midi.time_signature_changes) > 1:
            notices.append("tsov MIDI importer uses the first time signature only.")
        if any(inst.pitch_bends or inst.control_changes for inst in midi.instruments):
            notices.append("tsov does not guarantee CC/pitch-bend round-trip preservation.")

    write_midi(midi, dst, overwrite=overwrite)
    return BridgeReport(
        target=target, output=dst, tracks=len(midi.instruments),
        notes=sum(len(inst.notes) for inst in midi.instruments),
        quantized_notes=quantized, warnings=tuple(notices),
    )
