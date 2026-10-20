"""Invoke published Anticipatory Music Transformer conditioned on local MIDI."""
from __future__ import annotations
import argparse
import random
import sys
from pathlib import Path

def main():
    p = argparse.ArgumentParser()
    for name in ("checkout", "checkpoint", "source", "out"):
        p.add_argument("--" + name, required=True)
    p.add_argument("--melody-program", type=int, required=True)
    p.add_argument("--seconds", type=float, required=True)
    p.add_argument("--top-p", type=float, required=True)
    p.add_argument("--seed", type=int)
    a = p.parse_args()
    sys.path.insert(0, str(Path(a.checkout).resolve(strict=True)))
    import pretty_midi
    import torch
    from transformers import AutoModelForCausalLM
    from anticipation.convert import midi_to_events, events_to_midi
    from anticipation.tokenize import extract_instruments
    from anticipation.sample import generate

    original = pretty_midi.PrettyMIDI(a.source)
    if not any(inst.program == a.melody_program and inst.notes and not inst.is_drum
               for inst in original.instruments):
        raise ValueError("Selected melody program is absent in source MIDI")
    all_events = midi_to_events(a.source)
    _, melody_controls = extract_instruments(all_events, [a.melody_program])
    if not melody_controls:
        raise ValueError("Selected program produced no model control events")
    if a.seed is not None:
        random.seed(a.seed)
        torch.manual_seed(a.seed)
    model = AutoModelForCausalLM.from_pretrained(
        a.checkpoint, local_files_only=True, trust_remote_code=False)
    device = "cuda" if torch.cuda.is_available() else (
        "mps" if torch.backends.mps.is_available() else "cpu")
    model.to(device).eval()
    with torch.no_grad():
        accompaniment = generate(
            model, start_time=0, end_time=a.seconds,
            inputs=[], controls=melody_controls, top_p=a.top_p)
    if not accompaniment:
        raise ValueError("Model generated no accompaniment events")
    midi = events_to_midi(accompaniment)
    midi.save(a.out)

if __name__ == "__main__":
    main()
