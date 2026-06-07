"""
Day 5 — WebSocket voice endpoint end-to-end test.
Run AFTER implementing backend/routes/voice.py.

Prerequisites:
  1. All three API keys set in voice-agent/.env
  2. Backend server running:
       cd voice-agent/backend && uvicorn main:app --reload

Run:
    python tests/test_websocket.py --sample        # downloads Deepgram sample wav
    python tests/test_websocket.py --file audio.wav
    python tests/test_websocket.py --sample --save # saves received audio to file

Protocol this test expects from routes/voice.py:
  - WebSocket endpoint at:  ws://localhost:8000/ws/voice
  - Client sends:           binary frames (raw PCM audio chunks)
  - Server sends:           binary frames (MP3 audio from TTS)
  - Server signals end:     JSON frame {"type": "response_done"} after last audio chunk

Latency targets:
  - First audio frame back: ≤ 1,500 ms from last audio sent  (full round-trip)
  - Measured from when the last wav chunk is sent (simulates silence / utterance end)

Expected output:
  Connected to ws://localhost:8000/ws/voice
  Streaming 17.3s WAV (100 ms chunks) ...
  [rx]  2,048 bytes audio  @ 1,243 ms
  [rx]  3,072 bytes audio  @ 1,380 ms
  ...
  Done. Round-trip: 1,243 ms ✓  |  12 chunks, 24,576 bytes received
  Saved to test_ws_response.mp3
"""
import asyncio
import argparse
import sys
import os
import wave
import time
import json

ROOT = os.path.join(os.path.dirname(__file__), "..")

try:
    import websockets
except ImportError:
    print("ERROR: websockets not installed. Run: pip install websockets")
    sys.exit(1)

try:
    import httpx
except ImportError:
    httpx = None

WS_URL = "ws://localhost:8000/ws/voice"
CHUNK_MS = 100
SAMPLE_WAV_URL = "https://dpgr.am/spacewalk.wav"
ROUND_TRIP_TARGET_MS = 1500


async def download_sample(dest: str = "sample.wav") -> str:
    if httpx is None:
        print("ERROR: httpx not installed. Run: pip install httpx")
        sys.exit(1)
    print(f"Downloading sample from {SAMPLE_WAV_URL} ...")
    async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
        r = await client.get(SAMPLE_WAV_URL)
        r.raise_for_status()
    with open(dest, "wb") as f:
        f.write(r.content)
    print(f"Saved to {dest}")
    return dest


TARGET_RATE = 16000   # must match DeepgramSTT _LIVE_OPTIONS sample_rate

def wav_chunks(path: str, chunk_ms: int):
    """Yield 16 kHz mono linear16 PCM chunks resampled from the source WAV."""
    import audioop
    with wave.open(path, "rb") as wf:
        src_rate = wf.getframerate()
        src_ch   = wf.getnchannels()
        sw       = wf.getsampwidth()
        duration = wf.getnframes() / src_rate
        print(f"WAV: {src_ch}ch, {sw*8}-bit, {src_rate} Hz, {duration:.1f}s")
        print(f"Resampling to {TARGET_RATE} Hz mono, streaming {chunk_ms} ms chunks ...")

        frames_per_chunk = int(src_rate * chunk_ms / 1000)
        rs_state = None   # audioop.ratecv state

        while True:
            raw = wf.readframes(frames_per_chunk)
            if not raw:
                break
            # Mix down to mono if stereo
            if src_ch == 2:
                raw = audioop.tomono(raw, sw, 0.5, 0.5)
            # Resample to TARGET_RATE
            raw, rs_state = audioop.ratecv(raw, sw, 1, src_rate, TARGET_RATE, rs_state)
            yield raw


async def run(wav_path: str, save: bool):
    print(f"\nConnecting to {WS_URL} ...")

    try:
        async with websockets.connect(WS_URL, max_size=10 * 1024 * 1024) as ws:
            print("Connected.\n")

            received_chunks: list[bytes] = []
            t_last_sent: float | None = None
            t_first_rx: float | None = None
            done_event = asyncio.Event()

            async def receive_loop():
                nonlocal t_first_rx
                try:
                    async for msg in ws:
                        elapsed_ms = (time.perf_counter() - t_last_sent) * 1000 \
                            if t_last_sent else 0
                        if isinstance(msg, bytes):
                            if t_first_rx is None:
                                t_first_rx = elapsed_ms
                            received_chunks.append(msg)
                            print(f"  [rx] {len(msg):6,} bytes audio  @ {elapsed_ms:.0f} ms")
                        elif isinstance(msg, str):
                            data = json.loads(msg)
                            if data.get("type") == "response_done":
                                print(f"  [rx] response_done signal")
                                done_event.set()
                                break
                except websockets.exceptions.ConnectionClosed:
                    done_event.set()

            rx_task = asyncio.create_task(receive_loop())

            for chunk in wav_chunks(wav_path, CHUNK_MS):
                await ws.send(chunk)
                t_last_sent = time.perf_counter()
                await asyncio.sleep(CHUNK_MS / 1000)

            print("Audio sent. Waiting for response ...")

            try:
                await asyncio.wait_for(done_event.wait(), timeout=12.0)
            except asyncio.TimeoutError:
                print("WARN: timed out waiting for response_done — server may not send it yet")
                rx_task.cancel()

    except ConnectionRefusedError:
        print("ERROR: connection refused — is the backend server running?")
        print("       Start it: cd voice-agent/backend && uvicorn main:app --reload")
        sys.exit(1)

    print(f"\n{'-' * 55}")
    total_bytes = sum(len(c) for c in received_chunks)

    if t_first_rx is not None:
        status = "OK" if t_first_rx <= ROUND_TRIP_TARGET_MS else "WARN: slow"
        print(f"Round-trip latency : {t_first_rx:.0f} ms  (target <= {ROUND_TRIP_TARGET_MS} ms)  {status}")
    else:
        print("Round-trip latency : no audio received")

    print(f"Audio received     : {len(received_chunks)} chunks, {total_bytes:,} bytes")

    if received_chunks and save:
        out = "test_ws_response.mp3"
        with open(out, "wb") as f:
            for c in received_chunks:
                f.write(c)
        print(f"Saved to {out}")

    if not received_chunks:
        print("\nWARN: No audio frames received.")
        print("   Check that voice.py WebSocket endpoint is wired up (Day 5).")
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test WebSocket voice endpoint")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--file",   help="Path to a .wav file to stream")
    group.add_argument("--sample", action="store_true",
                       help="Download and use Deepgram's sample wav")
    parser.add_argument("--save",  action="store_true",
                        help="Save received audio to test_ws_response.mp3")
    parser.add_argument("--url", default=WS_URL,
                        help=f"WebSocket URL (default: {WS_URL})")
    args = parser.parse_args()

    WS_URL = args.url
    wav = args.file
    if args.sample:
        wav = asyncio.run(download_sample())

    asyncio.run(run(wav, args.save))
