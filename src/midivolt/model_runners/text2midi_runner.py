"""Invoke published Text2midi Transformer with explicitly provisioned local assets."""
from __future__ import annotations
import argparse
import pickle
import random
import sys
from pathlib import Path

# Support both direct isolated script execution and installed-package imports.
if __package__:
    from .text2midi_local import (
        inspect_local_t5, inspect_upstream_text2midi_contract,
        redirect_known_t5_encoder,
    )
else:
    from text2midi_local import (
        inspect_local_t5, inspect_upstream_text2midi_contract,
        redirect_known_t5_encoder,
    )

def main():
    p = argparse.ArgumentParser()
    for name in ("checkout", "checkpoint", "vocab", "t5-dir", "prompt", "out"):
        p.add_argument("--" + name, required=True)
    p.add_argument("--temperature", type=float, required=True)
    p.add_argument("--max-tokens", type=int, required=True)
    p.add_argument("--seed", type=int)
    a = p.parse_args()
    inspect_local_t5(a.t5_dir)
    inspect_upstream_text2midi_contract(a.checkout)
    sys.path.insert(0, str(Path(a.checkout).resolve(strict=True)))
    import torch
    from transformers import T5Tokenizer, T5EncoderModel
    from model.transformer_model import Transformer

    if a.seed is not None:
        random.seed(a.seed)
        torch.manual_seed(a.seed)
    device = "cuda" if torch.cuda.is_available() else (
        "mps" if torch.backends.mps.is_available() else "cpu")
    # Pickle may execute code: operator MUST verify provenance of this local file.
    with Path(a.vocab).open("rb") as stream:
        remi = pickle.load(stream)
    # Upstream Transformer.__init__ calls T5EncoderModel.from_pretrained
    # with a hardcoded HF model ID. Resolve only that request to local
    # operator-supplied encoder assets so offline runs cannot download it.
    with redirect_known_t5_encoder(T5EncoderModel, a.t5_dir):
        model = Transformer(len(remi), 768, 8, 2048, 18, 1024,
                            False, 8, device=device)
    state = torch.load(a.checkpoint, map_location=device, weights_only=True)
    model.load_state_dict(state)
    model.to(device).eval()
    tokenizer = T5Tokenizer.from_pretrained(a.t5_dir, local_files_only=True)
    encoded = tokenizer(a.prompt, return_tensors="pt", padding=True, truncation=True)
    with torch.no_grad():
        token_ids = model.generate(
            encoded["input_ids"].to(device),
            encoded["attention_mask"].to(device),
            max_len=a.max_tokens, temperature=a.temperature)
    midi = remi.decode(token_ids[0].tolist())
    midi.dump_midi(a.out)

if __name__ == "__main__":
    main()
