"""Benchmark F5 inference across device/precision combos on this machine.

The default F5 runtime is CPU + float32 (reliable on Apple Silicon). This script
times the alternatives so you can decide whether to flip ``f5_device`` in
``.env``. It loads the model fresh per combo and synthesizes a fixed sentence
for one reference voice, printing wall-clock time + real-time factor (RTF) and
writing each WAV so you can A/B listen for slurring.

Run from ``backend/``:

    uv run python scripts/bench_f5.py
    uv run python scripts/bench_f5.py --voice David --combos cpu/float32 mps/float32

Note: each combo downloads/loads the model once, so the first run is slower.
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from app.config import get_settings
from app.providers.f5_provider import F5Provider

# A ~20-word sentence with the kind of clauses that expose slurring.
_SENTENCE = (
    "Welcome back to another episode. Tonight we drift gently into the quiet, "
    "where the mind softens and the breath slows down."
)


def _run(combo: str, *, assets_dir: Path, voice: str, out_dir: Path) -> None:
    device, dtype = combo.split("/")
    provider = F5Provider(assets_dir=assets_dir, device=device, dtype=dtype)
    # Warm the model load out of the timed section.
    t0 = time.perf_counter()
    seg = provider.synthesize(_SENTENCE, voice, output_format="wav")
    elapsed = time.perf_counter() - t0
    audio_s = len(seg) / 1000.0
    rtf = elapsed / audio_s if audio_s else float("inf")
    out_path = out_dir / f"bench_{device}_{dtype}.wav"
    seg.export(out_path, format="wav")
    print(
        f"{combo:18s}  {elapsed:6.1f}s for {audio_s:5.1f}s audio  "
        f"RTF={rtf:4.2f}  -> {out_path}"
    )


def main() -> None:
    settings = get_settings()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--voice", default="David", help="reference voice slug")
    parser.add_argument(
        "--combos",
        nargs="+",
        default=["cpu/float32", "mps/float32"],
        help="device/dtype combos, e.g. cpu/float32 mps/float32 mps/float16",
    )
    parser.add_argument("--out", default="/tmp/f5_bench", help="output dir for WAVs")
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"Benchmarking F5 (voice={args.voice}); lower RTF is faster.\n")
    for combo in args.combos:
        try:
            _run(combo, assets_dir=settings.assets_dir, voice=args.voice, out_dir=out_dir)
        except Exception as exc:  # noqa: BLE001 - report and continue to next combo
            print(f"{combo:18s}  FAILED: {exc}")


if __name__ == "__main__":
    main()
