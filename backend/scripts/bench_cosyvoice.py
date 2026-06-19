"""Render a CosyVoice3 (MLX) sleep sample for A/B listening vs F5.

CosyVoice3's Instruct Mode drives delivery independently of the cloned clip's
energy. This script synthesizes one reference voice with the sleep directive so
you can judge whether the calm, hypnotic narration beats F5 *before* flipping any
default. It prints wall-clock time + real-time factor (RTF) and writes the WAV.

Run from ``backend/`` (needs ``uv sync --extra mlx``, Apple Silicon):

    uv run python scripts/bench_cosyvoice.py
    uv run python scripts/bench_cosyvoice.py --voice David --instruct "Speak slowly and calmly."

Pass ``--instruct ""`` to hear plain zero-shot cloning (no delivery directive).
Note: the first run downloads the model (~1.1 GB) and is slower.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# Make the backend package importable when run as `python scripts/bench_*.py`.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings  # noqa: E402
from app.providers.cosyvoice_provider import CosyVoiceProvider  # noqa: E402

# A few calm sentences with the kind of clauses that expose rushed delivery.
_SENTENCE = (
    "The old lighthouse stood at the edge of the bay. Its lamp turned slowly "
    "through the mist, and the tide breathed in and out against the smooth stones."
)


def main() -> None:
    settings = get_settings()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--voice", default="David", help="reference voice slug")
    parser.add_argument(
        "--instruct",
        default=settings.cosyvoice_sleep_instruct,
        help="delivery directive (instruct mode); pass '' for plain zero-shot",
    )
    parser.add_argument("--out", default="/tmp/cosyvoice_bench", help="output dir")
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    provider = CosyVoiceProvider(assets_dir=settings.assets_dir, model=settings.cosyvoice_model)
    vs = {"instruct": args.instruct} if args.instruct else None

    print(f"Synthesizing CosyVoice3 (voice={args.voice}); lower RTF is faster.\n")
    t0 = time.perf_counter()
    try:
        seg = provider.synthesize(_SENTENCE, args.voice, output_format="wav", voice_settings=vs)
    except Exception as exc:  # noqa: BLE001
        print(f"FAILED: {exc}")
        return
    elapsed = time.perf_counter() - t0
    audio_s = len(seg) / 1000.0
    rtf = elapsed / audio_s if audio_s else float("inf")
    out_path = out_dir / f"bench_cosyvoice_{args.voice}.wav"
    seg.export(out_path, format="wav")
    print(f"{elapsed:6.1f}s for {audio_s:5.1f}s audio  RTF={rtf:4.2f}  -> {out_path}")


if __name__ == "__main__":
    main()
