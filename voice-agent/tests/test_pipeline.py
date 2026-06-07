"""
Day 4+3 — Text-level pipeline test: transcript → LLM → TTS → audio.
Tests the LLM and TTS working together with sentence-level streaming,
without needing Deepgram or the WebSocket endpoint.

Run AFTER implementing both services/llm.py AND services/tts.py.

Requires in voice-agent/.env:
    ANTHROPIC_API_KEY=...
    ELEVENLABS_API_KEY=...

Run:
    python tests/test_pipeline.py
    python tests/test_pipeline.py --save     # saves audio files per turn

This test validates the key latency optimisation: TTS starts streaming
each sentence as it comes out of the LLM rather than waiting for the
full response. Target: first audio chunk < 900 ms from LLM start.

Expected output:
    Turn 1: "Hi, what can you help me with today?"
      [LLM] ........
      [LLM] "I can help you book appointments..." (645 ms)
      [TTS] first audio chunk @ 721 ms from LLM start  ✓
      [TTS] 5 chunks, 10,240 bytes
    ...
    Pipeline summary
      3 turns, avg LLM→first-audio: 734 ms  ✓
"""
import asyncio
import sys
import os
import time
import argparse

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "backend"))

from dotenv import load_dotenv
load_dotenv(dotenv_path=os.path.join(ROOT, ".env"))

ANTHROPIC_API_KEY    = os.getenv("ANTHROPIC_API_KEY", "")
ELEVENLABS_API_KEY   = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID  = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")

FIRST_AUDIO_TARGET_MS = 900   # LLM start → first TTS audio chunk

SYSTEM_PROMPT = (
    "You are a helpful voice assistant for a scheduling service. "
    "Reply in 1–2 natural spoken sentences, under 35 words. "
    "Use tools when appropriate."
)

TOOLS = [
    {
        "name": "book_appointment",
        "description": "Book a calendar appointment for the caller.",
        "input_schema": {
            "type": "object",
            "properties": {
                "date":  {"type": "string"},
                "time":  {"type": "string"},
                "name":  {"type": "string"},
                "email": {"type": "string"},
            },
            "required": ["date", "time", "name"],
        },
    }
]

SCRIPT = [
    "Hi, what can you help me with today?",
    "I'd like to book an appointment for next Tuesday at 10am.",
    "My name is Alex Johnson, email alex@example.com.",
]

# Sentence boundaries — split LLM output here to feed TTS progressively
_SENTENCE_ENDS = (".", "!", "?", ":")


def _split_sentences(buffer: str) -> tuple[list[str], str]:
    """Split completed sentences from buffer, return (sentences, remainder)."""
    sentences = []
    while True:
        idx = -1
        for sep in _SENTENCE_ENDS:
            pos = buffer.find(sep)
            if pos != -1 and (idx == -1 or pos < idx):
                idx = pos
        if idx == -1:
            break
        sentence = buffer[: idx + 1].strip()
        buffer = buffer[idx + 1 :]
        if sentence:
            sentences.append(sentence)
    return sentences, buffer


async def run_turn(
    llm,
    tts,
    messages: list[dict],
    turn_idx: int,
    save: bool,
) -> dict:
    user_text = messages[-1]["content"]
    print(f"\nTurn {turn_idx}: \"{user_text}\"")

    t_llm_start = time.perf_counter()
    response_text = ""
    sentence_buffer = ""
    tool_calls = []
    audio_chunks = []
    t_first_audio = None

    async def flush_sentence(sentence: str):
        nonlocal t_first_audio
        async for chunk in tts.stream(sentence):
            if t_first_audio is None:
                t_first_audio = (time.perf_counter() - t_llm_start) * 1000
            audio_chunks.append(chunk)

    print("  [LLM] streaming", end="", flush=True)

    async for event in llm.chat(messages=messages, system=SYSTEM_PROMPT, tools=TOOLS):
        if event["type"] == "text":
            response_text += event["text"]
            sentence_buffer += event["text"]
            print(".", end="", flush=True)

            # Kick off TTS for each completed sentence (key latency optimisation)
            sentences, sentence_buffer = _split_sentences(sentence_buffer)
            for s in sentences:
                await flush_sentence(s)

        elif event["type"] == "tool_use":
            tool_calls.append(event)
            print(f"\n  [tool] {event['name']}({event['input']})", flush=True)

    # Flush any trailing text that didn't end with punctuation
    if sentence_buffer.strip():
        await flush_sentence(sentence_buffer.strip())

    t_llm_done_ms = (time.perf_counter() - t_llm_start) * 1000

    print(f"\n  [LLM] \"{response_text.strip()}\"")
    print(f"  [LLM] total: {t_llm_done_ms:.0f} ms")

    if t_first_audio is not None:
        status = "OK" if t_first_audio <= FIRST_AUDIO_TARGET_MS else "WARN: slow"
        print(f"  [TTS] first audio chunk @ {t_first_audio:.0f} ms from LLM start  {status}")
    else:
        print("  [TTS] no audio received — TTS service may not be streaming yet")

    total_bytes = sum(len(c) for c in audio_chunks)
    print(f"  [TTS] {len(audio_chunks)} chunks, {total_bytes:,} bytes")

    if save and audio_chunks:
        path = f"test_pipeline_turn_{turn_idx}.mp3"
        with open(path, "wb") as f:
            for c in audio_chunks:
                f.write(c)
        print(f"  [TTS] saved to {path}")

    return {
        "turn": turn_idx,
        "first_audio_ms": t_first_audio,
        "llm_ms": t_llm_done_ms,
        "audio_bytes": total_bytes,
    }


async def run(save: bool):
    for key, name in [
        (ANTHROPIC_API_KEY,  "ANTHROPIC_API_KEY"),
        (ELEVENLABS_API_KEY, "ELEVENLABS_API_KEY"),
    ]:
        if not key or key in ("placeholder", "stub", "..."):
            print(f"ERROR: {name} is not set in voice-agent/.env")
            sys.exit(1)

    from services.llm import ClaudeLLM
    from services.tts import ElevenLabsTTS

    llm = ClaudeLLM(api_key=ANTHROPIC_API_KEY)
    tts = ElevenLabsTTS(api_key=ELEVENLABS_API_KEY, voice_id=ELEVENLABS_VOICE_ID)

    messages: list[dict] = []
    results = []

    for i, user_text in enumerate(SCRIPT, 1):
        messages.append({"role": "user", "content": user_text})
        metrics = await run_turn(llm, tts, messages.copy(), i, save)
        results.append(metrics)
        # Add assistant reply to history (use LLM's text for simplicity)
        messages.append({"role": "assistant", "content": ""})

    print(f"\n{'-' * 55}")
    print("Pipeline summary")
    valid = [r for r in results if r["first_audio_ms"] is not None]
    if valid:
        avg = sum(r["first_audio_ms"] for r in valid) / len(valid)
        over = [r for r in valid if r["first_audio_ms"] > FIRST_AUDIO_TARGET_MS]
        status = "OK" if not over else f"WARN: {len(over)} turn(s) over target"
        print(f"  {len(results)} turns, avg LLM->first-audio: {avg:.0f} ms  {status}")
    else:
        print("  No audio received — check TTS service implementation")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test LLM→TTS pipeline latency")
    parser.add_argument("--save", action="store_true",
                        help="Save TTS audio to test_pipeline_turn_N.mp3")
    args = parser.parse_args()
    asyncio.run(run(args.save))
