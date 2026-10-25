"""Invoke published Text2midi Transformer with explicitly provisioned local assets."""
from __future__ import annotations
import argparse
import json
import time
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
    for name in ("checkout", "checkpoint", "vocab", "t5-dir"):
        p.add_argument("--" + name, required=True)
    p.add_argument("--prompt")
    p.add_argument("--out")
    p.add_argument("--load-only", action="store_true",
                   help="Opt-in model weights/architecture load; do not generate MIDI")
    p.add_argument("--temperature", type=float, default=0.9)
    p.add_argument("--max-tokens", type=int, default=2000)
    p.add_argument("--seed", type=int)
    a = p.parse_args()
    if not a.load_only and (not a.prompt or not a.prompt.strip() or not a.out):
        p.error("Generation requires --prompt and --out unless --load-only is set.")
    if a.load_only and (a.out is not None or a.prompt is not None):
        p.error("--load-only does not accept MIDI output or prompt arguments.")
    if not 0.1 <= a.temperature <= 2.0 or not 32 <= a.max_tokens <= 4096:
        p.error("Invalid temperature or max-token count.")
    started = time.monotonic()
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
    if not isinstance(state, dict) or not state:
        raise RuntimeError("Trusted checkpoint must contain a nonempty state dictionary.")
    # Do not allow silent missing/unexpected key fallback.
    model.load_state_dict(state, strict=True)
    del state
    model.to(device).eval()
    # Load the local tokenizer even in --load-only mode: catches the common
    # tokenizer/model provision mismatch before expensive generation.
    tokenizer = T5Tokenizer.from_pretrained(a.t5_dir, local_files_only=True)
    if a.load_only:
        result = {
            "schema_version": 1,
            "model": "text2midi",
            "mode": "trusted_local_load_only",
            "model_state_dict_strict_loaded": True,
            "local_t5_encoder_initialized": True,
            "local_t5_tokenizer_initialized": True,
            "remi_pickle_deserialized": True,
            "upstream_model_code_imported": True,
            "pretrained_inference_executed": False,
            "midi_written": False,
            "device_type": device,
            "torch_version": str(torch.__version__),
            "vocab_size": len(remi),
            "model_parameter_count": sum(p.numel() for p in model.parameters()),
            "load_wall_seconds": round(time.monotonic() - started, 4),
            "pretrained_model_provenance_independently_attested": False,
            "commercial_release_ready": False,
        }
        print(json.dumps(result, sort_keys=True), flush=True)
        return
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
