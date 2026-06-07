"""
Day 3 — ElevenLabs TTS streaming test.
Run AFTER implementing backend/services/tts.py (ElevenLabsTTS class).

Requires in voice-agent/.env:
    ELEVENLABS_API_KEY=...
    ELEVENLABS_VOICE_ID=...  (default: Rachel, 21m00Tcm4TlvDq8ikWAM)

Run:
    python tests/test_tts.py
    python tests/test_tts.py --text "Custom sentence here."
    python tests/test_tts.py --all         # run all test sentences

Expected output:
    Synthesising: "Hello, this is a test..."
    [chunk  1]   1,024 bytes  @  318 ms
    [chunk  2]   2,048 bytes  @  401 ms
    ...
    Done. 6 chunks, 12,288 bytes, first-chunk latency: 318 ms  ✓

ElevenLabsTTS interface this test expects (services/tts.py):
    class ElevenLabsTTS:
        def __init__(self, api_key: str, voice_id: str)
        async def stream(self, text: str) -> AsyncGenerator[bytes, None]
"""
import asyncio
import argparse
import sys
import os
import time

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "backend"))

from dotenv import load_dotenv
load_dotenv(dotenv_path=os.path.join(ROOT, ".env"))

ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")

FIRST_CHUNK_TARGET_MS = 600  # ElevenLabs turbo model target

TEST_SENTENCES = [
    "Hello! This is a test of the ElevenLabs text-to-speech streaming system.",
    "I can help you book appointments, answer questions, or connect you with our team.",
    "Please hold while I look that up for you. It will only take a moment.",
    "Your appointment has been confirmed for Tuesday at 2pm. Is there anything else?",
]


async def synthesise_one(tts, text: str, save_path: str | None = None) -> dict:
    """Synthesise text, print chunk-by-chunk timing, return metrics dict."""
    print(f'\nSynthesising: "{text}"')

    chunks = []
    t_start = time.perf_counter()
    t_first = None

    async for chunk in tts.stream(text):
        elapsed_ms = (time.perf_counter() - t_start) * 1000
        if t_first is None:
            t_first = elapsed_ms
        chunks.append(chunk)
        print(f"  [chunk {len(chunks):2d}]  {len(chunk):6,} bytes  @  {elapsed_ms:.0f} ms")

    if not chunks:
        raise RuntimeError("No audio chunks received — check API key and voice ID")

    total_bytes = sum(len(c) for c in chunks)
    status = "OK" if t_first and t_first <= FIRST_CHUNK_TARGET_MS else "WARN: slow"
    print(f"  Done. {len(chunks)} chunks, {total_bytes:,} bytes, "
          f"first-chunk: {t_first:.0f} ms  {status}")

    if save_path:
        with open(save_path, "wb") as f:
            for c in chunks:
                f.write(c)
        print(f"  Saved to {save_path}")

    return {"chunks": len(chunks), "bytes": total_bytes, "first_ms": t_first}


async def run(text: str, run_all: bool, save: bool):
    if not ELEVENLABS_API_KEY or ELEVENLABS_API_KEY in ("...", "placeholder", "stub"):
        print("ERROR: ELEVENLABS_API_KEY is not set in voice-agent/.env")
        print("       Get your key at elevenlabs.io → Profile → API Keys")
        sys.exit(1)

    from services.tts import ElevenLabsTTS

    tts = ElevenLabsTTS(api_key=ELEVENLABS_API_KEY, voice_id=ELEVENLABS_VOICE_ID)
    print(f"Voice ID: {ELEVENLABS_VOICE_ID}")

    sentences = TEST_SENTENCES if run_all else [text]
    results = []

    for i, sentence in enumerate(sentences):
        save_path = f"test_tts_output_{i}.mp3" if save else None
        metrics = await synthesise_one(tts, sentence, save_path)
        results.append(metrics)

    print(f"\n{'-' * 55}")
    avg_first = sum(r["first_ms"] for r in results) / len(results)
    print(f"Sentences tested : {len(results)}")
    print(f"Avg first-chunk  : {avg_first:.0f} ms  (target <= {FIRST_CHUNK_TARGET_MS} ms)")
    slow = [r for r in results if r["first_ms"] > FIRST_CHUNK_TARGET_MS]
    if slow:
        print(f"WARN: {len(slow)} sentence(s) exceeded latency target")
    else:
        print("OK   All sentences within latency target")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test ElevenLabs TTS streaming")
    parser.add_argument("--text", default=TEST_SENTENCES[0],
                        help="Text to synthesise (default: first test sentence)")
    parser.add_argument("--all", action="store_true",
                        help="Run all test sentences")
    parser.add_argument("--save", action="store_true",
                        help="Save output to test_tts_output_N.mp3")
    args = parser.parse_args()
    asyncio.run(run(args.text, args.all, args.save))
