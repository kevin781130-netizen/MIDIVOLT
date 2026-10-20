"""Optional Spotify Basic Pitch integration (no runtime download by MIDIVOLT)."""

from __future__ import annotations

from pathlib import Path

from .io import write_midi


def transcribe_audio(
    source: str | Path, output: str | Path, *, overwrite: bool = False
) -> Path:
    source_path = Path(source)
    if not source_path.is_file():
        raise FileNotFoundError(source_path)
    # Validate output before expensive inference.
    output_path = Path(output)
    if output_path.suffix.lower() not in {".mid", ".midi"}:
        raise ValueError("Output must use .mid or .midi.")
    if output_path.exists() and not overwrite:
        raise FileExistsError(f"Refusing to overwrite {output_path}; use --overwrite.")
    try:
        from basic_pitch.inference import predict
    except ImportError as exc:
        raise RuntimeError(
            'Basic Pitch is optional. Install on Python 3.11 with: pip install -e ".[audio]"'
        ) from exc
    _, midi, _ = predict(str(source_path))
    return write_midi(midi, output_path, overwrite=overwrite)
