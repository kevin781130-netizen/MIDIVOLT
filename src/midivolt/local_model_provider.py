"""Local Text2midi implementation of MIDIVOLT's MidiGenerator contract.

Reuses the existing offline model subprocess. Model source, checkpoints,
vocabularies, and tokenizers are supplied by the operator; none are bundled.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from pathlib import Path
import tempfile

import pretty_midi

from .io import read_midi
from .model_adapters import generate_candidate


@dataclass(frozen=True)
class LocalText2MidiProvider:
    """Generate fresh MIDI with an explicitly provisioned local Text2midi model.

    Source tempo is used by composition_engine to align *beats*, not asserted
    as a model conditioning capability. Upstream inference may emit another BPM.
    """

    python_executable: str | Path
    checkout: str | Path
    checkpoint: str | Path
    vocab_path: str | Path
    t5_dir: str | Path
    timeout: float = 1200.0
    temperature: float = 0.9
    max_tokens: int = 2000
    name: str = "local-text2midi"

    def generate(
        self,
        prompt: str,
        *,
        tempo: float,
        seed: int | None = None,
    ) -> pretty_midi.PrettyMIDI:
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("Text2midi prompt must not be empty.")
        if not isinstance(tempo, (float, int)) or not isfinite(tempo) or not 1 <= tempo <= 500:
            raise ValueError("Source tempo must be finite and within 1..500 BPM.")
        if seed is not None and (type(seed) is not int or not 0 <= seed < 2**31):
            raise ValueError("Text2midi seed must be a nonnegative 31-bit integer.")

        # Existing adapter validates trusted local assets, enforces a timeout,
        # invokes the approved upstream model in a child process with shell=False,
        # and uses offline HF flags; no weights or API requests are bundled.
        with tempfile.TemporaryDirectory(prefix="midivolt-compose-model-") as tmp:
            output = Path(tmp) / "generated.mid"
            generate_candidate(
                model="text2midi",
                python_executable=self.python_executable,
                checkout=self.checkout,
                checkpoint=self.checkpoint,
                vocab_path=self.vocab_path,
                t5_dir=self.t5_dir,
                prompt=prompt,
                output_path=output,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                timeout=self.timeout,
                seed=seed,
            )
            return read_midi(output)
