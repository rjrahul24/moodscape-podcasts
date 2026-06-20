"""Reference-clip hygiene for voice cloning.

When a user uploads a short clip to clone, the raw recording often carries room
noise, fan hum, and dead air at the head/tail. The cloner (F5) copies
whatever they're given, so a noisy clip yields a noisy voice. This module cleans an
uploaded clip before it lands in the reference-voice registry.

The baseline (mono downmix, resample, silence trim, length cap) uses only pydub —
a base dependency — so upload + basic hygiene work out of the box. Denoising is an
optional enhancement (``uv sync --extra clean``, via ``noisereduce``) that degrades
to a no-op + a note when not installed, mirroring the providers' lazy philosophy.
Each step returns a human-readable note so the UI can show what was (and wasn't)
applied.
"""

from __future__ import annotations

import logging

import numpy as np
from pydub import AudioSegment
from pydub.silence import detect_leading_silence

from app.config import Settings

from .stitcher import numpy_to_segment

logger = logging.getLogger("moodscape")

_SILENCE_THRESH_DB = -45.0  # below this (relative to full scale) counts as silence
_CHUNK_MS = 10  # silence-detection granularity


def _trim_silence(seg: AudioSegment) -> tuple[AudioSegment, str | None]:
    """Trim leading/trailing near-silence (energy-based, no extra deps)."""
    lead = detect_leading_silence(seg, silence_threshold=_SILENCE_THRESH_DB, chunk_size=_CHUNK_MS)
    trail = detect_leading_silence(
        seg.reverse(), silence_threshold=_SILENCE_THRESH_DB, chunk_size=_CHUNK_MS
    )
    end = len(seg) - trail
    if lead == 0 and end >= len(seg):
        return seg, None
    if end <= lead:  # the whole clip read as silence — leave it untouched
        return seg, "silence trim skipped — clip read as all-silence"
    return seg[lead:end], f"trimmed {lead} ms head / {trail} ms tail of silence"


def _denoise(seg: AudioSegment, sample_rate: int) -> tuple[AudioSegment, str | None]:
    """Spectral-gate denoise via noisereduce; no-op + note when unavailable."""
    try:
        import noisereduce as nr
    except Exception as exc:  # noqa: BLE001 - optional extra not installed
        return seg, f"denoise skipped — noisereduce unavailable ({exc}); `uv sync --extra clean`"

    samples = np.array(seg.get_array_of_samples()).astype(np.float32)
    peak = float(np.max(np.abs(samples))) or 1.0
    try:
        reduced = nr.reduce_noise(y=samples / peak, sr=sample_rate)
    except Exception as exc:  # noqa: BLE001 - never fatal
        return seg, f"denoise skipped — failed ({exc})"
    return numpy_to_segment(reduced.astype(np.float32), sample_rate), "denoised (noisereduce)"


def _cap_length(seg: AudioSegment, max_seconds: float) -> tuple[AudioSegment, str | None]:
    """Cap the clip length — cloners only need a short reference window."""
    max_ms = int(max_seconds * 1000)
    if len(seg) <= max_ms:
        return seg, None
    return seg[:max_ms], f"trimmed to first {max_seconds:.0f}s (cloners need only a short clip)"


def clean_clip(src_path: str, dst_path: str, *, settings: Settings) -> list[str]:
    """Clean an uploaded clip and write a mono WAV to ``dst_path``.

    Pipeline: load → mono → resample → silence-trim → denoise (optional) → length
    cap → export. Returns the per-step notes (empty when everything applied
    cleanly). Raises only if the source can't be decoded at all.
    """
    rate = settings.reference_clip_sample_rate
    seg = AudioSegment.from_file(src_path)
    seg = seg.set_channels(1).set_frame_rate(rate)

    notes: list[str] = []
    seg, n = _trim_silence(seg)
    if n:
        notes.append(n)
    seg, n = _denoise(seg, rate)
    if n:
        notes.append(n)
    seg, n = _cap_length(seg, settings.reference_clip_max_seconds)
    if n:
        notes.append(n)

    seg.export(dst_path, format="wav")
    return notes
