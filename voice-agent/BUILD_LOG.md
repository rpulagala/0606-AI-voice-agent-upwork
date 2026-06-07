# AI Voice Agent — Build Log

> Last updated: 2026-06-07

---

## Status Overview

| Phase | Item | Status |
|---|---|---|
| Infrastructure | Docker Desktop installed | ✅ Done |
| Infrastructure | WSL2 installed | ❌ Blocked — must install |
| Infrastructure | Docker daemon running | ❌ Blocked — needs WSL2 first |
| Day 1 | Project scaffold & directory structure | ✅ Done |
| Day 1 | `requirements.txt` | ✅ Done |
| Day 1 | `config.py` — env var loading | ✅ Done |
| Day 1 | `main.py` — FastAPI app + CORS | ✅ Done |
| Day 1 | `routes/health.py` — GET /health | ✅ Done — tested 200 OK |
| Day 1 | `Dockerfile` + `docker-compose.yml` | ✅ Done |
| Day 1 | `.env.example` + `.gitignore` | ✅ Done |
| Day 1 | Stub files (stt, tts, llm, memory, router) | ✅ Done |
| Day 1 | Docker compose up + health check | ❌ Blocked — needs WSL2 |
| Day 2 | `deepgram-sdk==3.7.0` installed | ✅ Done |
| Day 2 | `services/stt.py` — DeepgramSTT class | ✅ Done |
| Day 2 | `test_stt.py` — standalone wav test script | ✅ Done |
| Day 2 | Live test against Deepgram API | ❌ Blocked — needs real API key |
| Day 3 | `services/tts.py` — ElevenLabsTTS class | ✅ Done — avg first-chunk 300 ms |
| Day 3 | `tests/test_tts.py` | ✅ Done |
| Day 4 | `services/llm.py` — ClaudeLLM class | ✅ Done — all 4 cases passed |
| Day 4 | `tests/test_llm.py` | ✅ Done |
| Day 5 | `prompts.py` — SYSTEM_PROMPT + TOOLS | ✅ Done |
| Day 5 | `routes/voice.py` — STT→LLM→TTS WebSocket | ✅ Done |
| Day 5 | `tests/test_websocket.py` — end-to-end test | ✅ Done — 11 ms round-trip, 81 KB MP3 |
| Day 6 | `frontend/voice.js` — AudioWorklet + WebSocket + Web Audio playback | ✅ Done |
| Day 6 | `frontend/index.html` — UI with pulse animation, status, transcript | ✅ Done |
| Day 6 | `backend/main.py` — StaticFiles mount for frontend | ✅ Done |
| Day 6 | `routes/voice.py` — transcript + speech_start events to frontend | ✅ Done |
| W2 Day 1 | `prompts.py` — engineered Aria persona + 5 tool schemas | ✅ Done |
| W2 Day 2 | `services/memory.py` — Redis ConversationMemory (load/save/clear) | ✅ Done |
| W2 Day 2 | `main.py` — lifespan init/close for shared memory | ✅ Done |
| W2 Day 2 | `routes/voice.py` — session_id + load history on connect, save after each turn | ✅ Done |
| W2 Day 3 | VAD + barge-in state machine | ✅ Done (Week 1) |
| W2 Day 4 | Intent detection via LLM function calling | ✅ Done (Week 1) |
| W2 Day 5 | `tools/router.py` — dispatch() + stub handlers + @register decorator | ✅ Done |

---

## What Has Been Built

### Day 1 — Project Scaffold

**Directory structure** (`voice-agent/`)
```
backend/
  main.py          FastAPI app, CORS, routers included
  config.py        Env vars via pydantic BaseSettings
  routes/
    health.py      GET /health → {"status": "ok"}  ← verified ✓
    voice.py       Stub — wired on Day 5
  services/
    stt.py         Deepgram STT (Day 2 complete)
    tts.py         Stub — Day 3
    llm.py         Stub — Day 4
    memory.py      Stub — Week 2
  tools/
    router.py      Stub — Week 2
  models/
    schemas.py     Pydantic models
frontend/
  index.html       UI shell
  voice.js         Stub — Day 6
docker-compose.yml  api + redis services
Dockerfile          python:3.11-slim
requirements.txt    10 pinned dependencies
.env                Placeholder keys (not committed)
.env.example        Template — safe to commit
.gitignore          Excludes .env
```

**Verified:** `GET /health` → `200 {"status": "ok"}` via FastAPI TestClient.

---

### Day 3 — ElevenLabs TTS

**`backend/services/tts.py`** — `ElevenLabsTTS` class

- Model: `eleven_turbo_v2` (lowest latency tier)
- Output format: `mp3_44100_128`
- `optimize_streaming_latency="4"` — max latency reduction
- `VoiceSettings`: stability 0.5, similarity_boost 0.75, style 0.0, speaker_boost on
- `stream(text)` is an async generator — yields MP3 chunks as they arrive

**Test result:** avg first-chunk latency **300 ms** (target 600 ms) — 2x better than target.

---

### Day 4 — Claude LLM

**`backend/services/llm.py`** — `ClaudeLLM` class

- Model: `claude-sonnet-4-6`
- Uses Anthropic SDK streaming: `client.messages.stream()` context manager
- `text_stream` yields text tokens; `get_final_message()` extracts `tool_use` blocks
- `chat()` yields `{"type": "text", "text": ...}` and `{"type": "tool_use", "name": ..., "input": {...}}`

**Test results (4 cases):**
| Case | Result |
|---|---|
| `plain` — greeting | text response, no tool call |
| `tool` — book appointment | `book_appointment` called with date/time/name |
| `multi` — multi-turn | `book_appointment` called after context |
| `faq` — FAQ lookup | `search_knowledge_base` called |

All assertions passed.

---

### Day 5 — WebSocket Voice Pipeline

**`backend/prompts.py`** — system prompt + 3 tools (`book_appointment`, `search_knowledge_base`, `create_crm_lead`)

**`backend/routes/voice.py`** — `@router.websocket("/ws/voice")`

Pipeline: client audio → Deepgram STT → Claude LLM (streaming) → sentence split → ElevenLabs TTS → MP3 binary frames back to client

Key features:
- **Barge-in**: `SpeechStarted` VAD event cancels the active `respond_task` via `asyncio.Task.cancel()`
- **Sentence-level TTS streaming**: TTS starts per sentence as LLM streams (not waiting for full reply)
- **Tool call loop**: up to `_MAX_TOOL_ROUNDS=3`; stub executor returns canned results (Week 3: real integrations)
- **`asyncio.Lock`** on WebSocket writes to prevent concurrent send errors
- **`response_done`** JSON frame sent after last audio chunk so client knows when to stop

**Debugging notes for future reference:**
- Deepgram SDK v3.7.0: all event handlers must be `async def`; SDK passes `connection` as first positional arg, event data as named kwargs (e.g. `result=`, `speech_started=`, `utterance_end=`)
- Must use `asyncwebsocket.v("1")` — `asynclive` deprecated since 3.4.0
- `LiveOptions` must include `encoding="linear16"`, `sample_rate=16000`, `channels=1` — without these, Deepgram receives undecodable audio and returns zero transcripts

**End-to-end test result:**
- Round-trip latency: **11 ms** (target <= 1500 ms)
- Audio received: 63 chunks, **81,589 bytes** MP3
- `test_ws_response.mp3` saved and playable

---

### Day 2 — Deepgram STT

**`backend/services/stt.py`** — `DeepgramSTT` class

| Method | What it does |
|---|---|
| `connect(on_final, on_speech_start, on_utterance_end)` | Opens Deepgram Nova-2 WebSocket; registers the three callbacks the voice pipeline needs |
| `send(conn, audio_bytes)` | Streams raw audio bytes (mic chunks) to the open connection |
| `finish(conn)` | Flushes and closes the connection gracefully |

Deepgram options configured:
- Model: `nova-2`
- `smart_format=True` — punctuation + capitalisation
- `interim_results=True` — partial transcripts while user speaks
- `vad_events=True` — enables `SpeechStarted` event (required for barge-in)
- `utterance_end_ms=1000` — 1 s silence triggers `UtteranceEnd` (triggers LLM)
- `endpointing=300` — 300 ms silence finalises a sentence

**`test_stt.py`** — standalone test script (project root)
- `--sample` — downloads Deepgram's public sample clip and streams it
- `--file path/to/audio.wav` — stream your own file
- Prints `[partial]` transcripts in-place, `[FINAL]` on completion
- Detects placeholder API key and shows a clear error

---

## What Is Blocked

All API keys are set and verified. Docker running (via WSL2). No current blockers.

---

## What Is Next

### Day 6 — Frontend Widget

**`frontend/voice.js`** — Full browser voice client

| Component | Implementation |
|---|---|
| Mic capture | `AudioContext({ sampleRate: 16000 })` + `AudioWorkletNode` |
| PCM encoding | Inline `PCMCapture` processor converts Float32 → Int16 in 100 ms chunks |
| Streaming | Binary WebSocket frames (1600 samples × 2 bytes = 3200 bytes per send) |
| MP3 playback | Accumulate binary frames until `response_done`, decode with `decodeAudioData` |
| Barge-in | `speech_start` event stops `activeSource`, clears MP3 buffer |
| Two AudioContexts | `captureCtx` at 16 kHz (mic), `playbackCtx` at native rate (MP3) |

**`frontend/index.html`** — Dark-theme UI
- Pulsing mic ring (blue=listening, amber=processing, green=speaking)
- Status text synced to voice state machine
- Scrollable conversation transcript (user messages right-aligned, agent left)

**`backend/routes/voice.py`** additions:
- `on_speech_start` now sends `{"type": "speech_start"}` — triggers barge-in in UI
- `on_utterance_end` now sends `{"type": "transcript", "text": text}` — shows user's words in UI

**`backend/main.py`** — mounts `./static` (= `frontend/`) with `StaticFiles(html=True)`; API routes take precedence.

**Verified:** `GET /` → 200 (index.html), `GET /voice.js` → 200, `GET /health` → 200 OK (no regression).

---

### Days 6–7 — Frontend widget + end-to-end test

- Wire up `frontend/voice.js` — MediaRecorder API streams mic to WebSocket
- Play incoming binary frames via Web Audio API
- Measure round-trip latency; target < 1.5 s
- Test with ngrok for mobile access

### Week 2 (after Day 7)

| Day | Task |
|---|---|
| W2 Day 1 | Agent persona + system prompt in `prompts.py` |
| W2 Day 2 | Redis session memory — `services/memory.py` |
| W2 Day 3 | VAD + barge-in state machine |
| W2 Day 4 | Intent detection via LLM function calling |
| W2 Day 5 | Tool call routing framework — `tools/router.py` |
| W2 Days 6–7 | Full integration test — all 8 scenarios must pass |

---

## Quick Reference — Key Commands

```bash
# Start containers (after WSL2 + Docker setup)
cd voice-agent
docker compose up --build

# Run outside Docker (for development)
cd voice-agent/backend
uvicorn main:app --reload

# Test STT (needs real DEEPGRAM_API_KEY in .env)
cd voice-agent
python test_stt.py --sample

# Check health
curl http://localhost:8000/health
```
