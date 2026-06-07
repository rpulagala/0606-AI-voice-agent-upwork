"""
Day 2 — Standalone Deepgram STT test
======================================
Streams a .wav file (or raw PCM bytes) to Deepgram and prints every
final transcript to stdout.

Usage
-----
  # stream a wav file
  python test_stt.py --file path/to/audio.wav

  # use the bundled sample (downloads a short clip from Deepgram's CDN)
  python test_stt.py --sample

Requirements
------------
  DEEPGRAM_API_KEY must be set in .env or the environment.
  pip install deepgram-sdk==3.7.0 python-dotenv httpx
"""

import asyncio
import argparse
import logging
import wave
import sys
import os

# Load .env so the key is available without Docker
from dotenv import load_dotenv
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))

from deepgram import DeepgramClient, DeepgramClientOptions, LiveTranscriptionEvents, LiveOptions

logging.basicConfig(level=logging.WARNING)

DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY", "")
CHUNK_MS = 100        # send audio in 100 ms chunks
SAMPLE_WAV_URL = "https://dpgr.am/spacewalk.wav"  # ~17 s Deepgram sample clip


# ── helpers ───────────────────────────────────────────────────────────────────

async def download_sample(dest: str = "sample.wav") -> str:
    import httpx
    print(f"Downloading sample from {SAMPLE_WAV_URL} ...")
    async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
        r = await client.get(SAMPLE_WAV_URL)
        r.raise_for_status()
    with open(dest, "wb") as f:
        f.write(r.content)
    print(f"Saved to {dest}")
    return dest


def wav_chunks(path: str, chunk_ms: int):
    """Yield raw PCM byte chunks from a wav file at the natural playback rate."""
    with wave.open(path, "rb") as wf:
        channels    = wf.getnchannels()
        sample_width = wf.getsampwidth()
        frame_rate  = wf.getframerate()
        frames_per_chunk = int(frame_rate * chunk_ms / 1000)
        print(f"WAV: {channels}ch, {sample_width*8}-bit, {frame_rate} Hz, "
              f"streaming {chunk_ms} ms chunks")
        while True:
            data = wf.readframes(frames_per_chunk)
            if not data:
                break
            yield data


# ── main test ─────────────────────────────────────────────────────────────────

async def run(wav_path: str):
    if not DEEPGRAM_API_KEY or DEEPGRAM_API_KEY == "placeholder":
        print("ERROR: DEEPGRAM_API_KEY is not set in .env")
        print("       Sign up at https://console.deepgram.com and add your key to voice-agent/.env")
        sys.exit(1)

    transcripts = []
    done = asyncio.Event()

    config = DeepgramClientOptions(options={"keepalive": "true"})
    client = DeepgramClient(DEEPGRAM_API_KEY, config)
    conn   = client.listen.asyncwebsocket.v("1")

    async def on_transcript(_, result, **kwargs):
        t = result.channel.alternatives[0].transcript
        if result.is_final and t.strip():
            print(f"  [FINAL]   {t}")
            transcripts.append(t)
        elif t.strip():
            print(f"  [partial] {t}", end="\r")

    async def on_error(_, error, **kwargs):
        print(f"\nDeepgram error: {error}")

    async def on_close(_, close, **kwargs):
        done.set()

    conn.on(LiveTranscriptionEvents.Transcript, on_transcript)
    conn.on(LiveTranscriptionEvents.Error,      on_error)
    conn.on(LiveTranscriptionEvents.Close,      on_close)

    options = LiveOptions(
        model="nova-2",
        language="en-US",
        encoding="linear16",
        sample_rate=44100,
        smart_format=True,
        interim_results=True,
        endpointing=300,
    )

    print(f"\nConnecting to Deepgram (nova-2) ...")
    started = await conn.start(options)
    if not started:
        print("ERROR: could not open Deepgram connection. Check your API key.")
        sys.exit(1)
    print("Connected. Streaming audio ...\n")

    # Stream the wav file in real-time chunks
    for chunk in wav_chunks(wav_path, CHUNK_MS):
        await conn.send(chunk)
        await asyncio.sleep(CHUNK_MS / 1000)   # simulate real-time playback

    await asyncio.sleep(1.5)   # let Deepgram flush final transcripts
    await conn.finish()
    await asyncio.wait_for(done.wait(), timeout=5)

    print(f"\n{'-'*50}")
    print(f"Done. {len(transcripts)} final transcript(s) received.")
    if transcripts:
        print("\nFull transcript:")
        print(" ".join(transcripts))
    else:
        print("No transcripts returned - check audio content and API key.")


# ── entrypoint ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test Deepgram STT with a wav file")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--file",   help="Path to a .wav file")
    group.add_argument("--sample", action="store_true",
                       help="Download and use Deepgram's sample audio clip")
    args = parser.parse_args()

    wav_path = args.file
    if args.sample:
        wav_path = asyncio.run(download_sample())

    asyncio.run(run(wav_path))
