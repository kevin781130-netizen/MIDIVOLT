"""Typed contract for future commercial-rights-reviewed generation models.

No neural generator is bundled or implied by this module.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import pretty_midi


@runtime_checkable
class MidiGenerator(Protocol):
    """Implement this contract for each installed text/continuation model."""

    name: str

    def generate(self, prompt: str, *, tempo: float, seed: int | None = None) -> pretty_midi.PrettyMIDI:
        """Return a fully encoded MIDI object or raise an explicit error."""
        ...
