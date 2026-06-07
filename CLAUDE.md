# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

All commands run from the `voice-agent/` directory unless noted.

```bash
# Run the backend in dev mode (outside Docker)
cd voice-agent/backend
uvicorn main:app --reload

# Start Docker stack (requires WSL2 + Docker Desktop running)
cd voice-agent
docker compose up --build

# Health check
curl http://localhost:8000/health

# Unit tests (no API keys needed — uses TestClient with stubbed env vars)
cd voice-agent
pytest tests/test_health.py -v

# Integration tests (require real API keys in voice-agent/.env)
python tests/test_tts.py              # ElevenLabs TTS chunks + latency
python tests/test_llm.py              # Claude streaming + tool calls (4 cases)
python tests/test_pipeline.py         # LLM → TTS sentence streaming, latency report
python tests/test_pipeline.py --save  # also writes per-turn MP3 files

# End-to-end WebSocket test (server must be running first)
python tests/test_websocket.py --sample        # downloads Deepgram sample wav
python tests/test_websocket.py --file audio.wav
python tests/test_websocket.py --sample --save # saves received audio to test_ws_response.mp3

# Standalone STT test (streams a wav to Deepgram, prints transcripts)
python test_stt.py --sample
python test_stt.py --file path/to/audio.wav
```

**Docker prerequisite (Windows):** WSL2 must be installed before Docker can start. Run `wsl --install` in an admin terminal, then restart. After restart, open Docker Desktop and wait ~60 s for the engine.

## Environment Variables

Copy `voice-agent/.env.example` to `voice-agent/.env` and fill in real keys:

| Key | Source |
|---|---|
| `ANTHROPIC_API_KEY` | console.anthropic.com |
| `DEEPGRAM_API_KEY` | console.deepgram.com |
| `ELEVENLABS_API_KEY` | elevenlabs.io → Profile → API Keys |
| `ELEVENLABS_VOICE_ID` | elevenlabs.io → Voices (project default: `FNuubxPir6An3aynywgf`) |

`config.py` loads these via pydantic-settings. Docker reads `.env` via `env_file`; dev server reads it via `python-dotenv` in pydantic_settings. `REDIS_URL` defaults to `redis://redis:6379`.

## Architecture

Real-time voice pipeline (target end-to-end latency < 1.5 s):

```
Browser mic → WebSocket /ws/voice → FastAPI (routes/voice.py)
    → Deepgram Nova-2 STT  (~200 ms)
    → Claude Sonnet 4.6 LLM  (~400 ms first token, streaming)
    → ElevenLabs eleven_turbo_v2 TTS  (~300 ms first chunk)
    → WebSocket binary MP3 frames back to browser
```

**Barge-in**: Deepgram's `SpeechStarted` VAD event fires when the user starts speaking mid-response. `on_speech_start` cancels the active `respond_task` (`asyncio.Task.cancel()`) and sends `{"type": "speech_start"}` to the client to stop playback.

**Turn trigger**: `UtteranceEnd` (1500 ms silence) signals the LLM to respond. `is_final` transcripts accumulate the turn text in `transcript_buffer`.

**Sentence-level TTS**: `_split_sentences()` in `voice.py` pops completed sentences from the LLM token stream. TTS starts per sentence — first audio arrives before the LLM finishes.

**Tool call loop**: up to `_MAX_TOOL_ROUNDS = 3` in `voice.py`. Tool stubs in `_run_tool()` return canned strings. Week 3: replace with real integrations under `tools/`.

**Session memory**: Redis — `services/memory.py` is a stub (Week 2 Day 2). Full history in PostgreSQL is planned.

**Module imports**: `backend/` is the Docker working directory (`WORKDIR /app`, `COPY backend/ .`). Imports are always relative to `backend/` — e.g. `from routes.health import router`, never `from backend.routes.health`.

**Frontend state machine** (`frontend/voice.js`): `IDLE → CONNECTING → LISTENING → PROCESSING → SPEAKING → LISTENING`. Mic is gated off only during `SPEAKING` (not `PROCESSING`) to allow barge-in while the server is computing. Two `AudioContext`s: `captureCtx` at 16 kHz (mic via AudioWorklet `PCMCapture`), `playbackCtx` at native rate (MP3 decode via `decodeAudioData`). MP3 chunks accumulate until `response_done`, then decode + play.

## Build Status

| Component | File | Status |
|---|---|---|
| FastAPI app + CORS + static mount | `backend/main.py` | Done |
| Config / env loading | `backend/config.py` | Done |
| Health endpoint | `backend/routes/health.py` | Done |
| Deepgram STT | `backend/services/stt.py` | Done |
| ElevenLabs TTS | `backend/services/tts.py` | Done — avg first-chunk 300 ms |
| Claude LLM (streaming + tools) | `backend/services/llm.py` | Done |
| System prompt + tool schemas | `backend/prompts.py` | Done |
| WebSocket voice pipeline | `backend/routes/voice.py` | Done — 11 ms round-trip in test |
| Frontend widget + UI | `frontend/voice.js`, `frontend/index.html` | Done |
| Redis session memory | `backend/services/memory.py` | **Stub — Week 2 Day 2** |
| Tool call routing | `backend/tools/router.py` | **Stub — Week 2 Day 5** |

Detailed progress is in `voice-agent/BUILD_LOG.md`.

## Key Design Decisions & Gotchas

- **Deepgram SDK v3.7.0**: all event handlers must be `async def`. The SDK passes `connection` as the first positional arg and event data as named kwargs (`result=`, `speech_started=`, `utterance_end=`). Use `asyncwebsocket.v("1")` — `asynclive` is deprecated since 3.4.0.
- **Deepgram LiveOptions**: must include `encoding="linear16"`, `sample_rate=16000`, `channels=1`. Without these, Deepgram receives undecodable audio and returns zero transcripts. For Twilio/phone swap to `encoding="mulaw", sample_rate=8000`.
- **`asyncio.Lock` on WebSocket writes**: `ws_lock` in `voice.py` prevents concurrent `send_bytes` / `send_text` errors when TTS audio and control JSON frames race.
- **`response_done` frame**: JSON `{"type": "response_done"}` is sent after the last audio chunk so the client knows when to start playback (all chunks buffered).
- **TTS model**: `eleven_turbo_v2` with `optimize_streaming_latency="4"`. Output is `mp3_44100_128`.
- **LLM tool calls**: `ClaudeLLM.chat()` yields `text` tokens in real-time via `text_stream`, then yields `tool_use` blocks from `get_final_message()` after streaming completes. The `voice.py` loop handles up to 3 tool-call rounds before breaking.
