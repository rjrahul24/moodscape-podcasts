"""Benchmark long-form (30–90 min) synthesis per local provider on this machine.

The research claims long-form local generation is practical on an M1 Max but never
measures it. This script does: for each local provider it builds increasingly long
narration, chunks it exactly like the orchestrator, synthesizes every chunk, and
reports wall-clock, real-time factor (RTF), and peak resident memory (RSS).

Watch for two things:
  * RTF should stay < 1.0 (faster than real time) and not creep upward as length
    grows.
  * Peak RSS should plateau, not track audio length — disk-based stitching keeps
    the *output* off the heap, but the model + cache must stay bounded.

Run from ``backend/``:

    uv run python scripts/bench_longform.py
    uv run python scripts/bench_longform.py --providers f5 --minutes 30 60
    uv run python scripts/bench_longform.py --providers kokoro --minutes 5

The first run per provider downloads/loads the model.
"""

from __future__ import annotations

import argparse
import resource
import sys
import time
from pathlib import Path

# Make the backend package importable when run as `python scripts/bench_*.py`.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings  # noqa: E402
from app.core import chunker  # noqa: E402
from app.providers.f5_provider import F5Provider  # noqa: E402
from app.providers.kokoro_provider import KokoroProvider  # noqa: E402

# ~150 words/min is a calm narration rate; used to size text from a duration.
_WORDS_PER_MIN = 150

# One calm paragraph, repeated to reach the target word count. Sentence-final
# punctuation matters: the chunker splits on it, so this exercises real chunking.
_PARAGRAPH = (
    "The old lighthouse stood at the edge of the bay. Its lamp turned slowly "
    "through the mist, and the tide breathed in and out against the smooth stones. "
    "Somewhere far off a bell rang once, and then the quiet settled back over the "
    "water. Let your shoulders soften now, and let the breath find its own gentle "
    "rhythm, slow and unhurried, like the sea."
)


def _build_text(minutes: float) -> str:
    """Repeat the base paragraph until it reaches ~``minutes`` of narration."""
    target_words = int(minutes * _WORDS_PER_MIN)
    para_words = len(_PARAGRAPH.split())
    reps = max(1, -(-target_words // para_words))  # ceil division
    return " ".join([_PARAGRAPH] * reps)


def _peak_rss_mb() -> float:
    """Process peak RSS in MB. ``ru_maxrss`` is bytes on macOS, KiB on Linux."""
    maxrss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    divisor = 1024 * 1024 if sys.platform == "darwin" else 1024
    return maxrss / divisor


def _make_provider(name: str, settings) -> object:
    if name == "kokoro":
        return KokoroProvider(speed=settings.kokoro_speed)
    if name == "f5":
        return F5Provider(
            assets_dir=settings.assets_dir,
            speed=settings.f5_speed,
            device=settings.f5_device,
            dtype=settings.f5_dtype,
            nfe_step=settings.f5_nfe_step,
            cfg_strength=settings.f5_cfg_strength,
            sway_coef=settings.f5_sway_coef,
        )
    raise ValueError(f"unknown provider {name!r}")


def _voice_settings(name: str, settings) -> dict | None:
    """Mirror the sleep-path settings the orchestrator would send each provider."""
    if name in ("kokoro", "f5"):
        return {"speed": settings.sleep_default_speed}
    return None


def _bench(name: str, minutes_list: list[float], settings) -> None:
    provider = _make_provider(name, settings)
    voices = provider.list_voices()
    if not voices:
        print(f"{name}: no voices available (add reference clips?) — skipping")
        return
    voice_id = voices[0].id
    vs = _voice_settings(name, settings)
    overrides = {
        "kokoro": settings.kokoro_chunk_chars,
        "f5": settings.f5_chunk_chars,
    }
    budget = chunker.budget_for(name, overrides=overrides)

    print(f"\n{name}  (voice={voice_id}, chunk_chars={budget})")
    print(f"  {'target':>7}  {'chunks':>6}  {'audio':>8}  {'wall':>8}  {'RTF':>5}  {'peakRSS':>8}")
    for minutes in minutes_list:
        text = _build_text(minutes)
        chunks = chunker.chunk_text(text, budget)
        t0 = time.perf_counter()
        audio_ms = 0
        try:
            for piece in chunks:
                seg = provider.synthesize(
                    piece, voice_id, output_format="wav", voice_settings=vs
                )
                audio_ms += len(seg)
        except Exception as exc:  # noqa: BLE001 - report and move to next length
            print(f"  {minutes:6.0f}m  FAILED: {exc}")
            return
        wall = time.perf_counter() - t0
        audio_s = audio_ms / 1000.0
        rtf = wall / audio_s if audio_s else float("inf")
        print(
            f"  {minutes:6.0f}m  {len(chunks):6d}  {audio_s:7.1f}s  "
            f"{wall:7.1f}s  {rtf:5.2f}  {_peak_rss_mb():6.0f}MB"
        )


def main() -> None:
    settings = get_settings()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--providers",
        nargs="+",
        default=["kokoro", "f5"],
        help="local providers to benchmark",
    )
    parser.add_argument(
        "--minutes",
        nargs="+",
        type=float,
        default=[5, 15, 30],
        help="target narration lengths in minutes (try 30 60 for the full test)",
    )
    args = parser.parse_args()

    print("Long-form synthesis benchmark — lower RTF is faster; watch peak RSS.")
    for name in args.providers:
        try:
            _bench(name, args.minutes, settings)
        except Exception as exc:  # noqa: BLE001 - one provider failing shouldn't stop the rest
            print(f"\n{name}: setup FAILED: {exc}")


if __name__ == "__main__":
    main()
