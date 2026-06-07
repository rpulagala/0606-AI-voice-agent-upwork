# AI Voice Agent

A real-time, browser-based voice agent powered by Deepgram (STT), Claude Sonnet 4.6 (LLM), and ElevenLabs (TTS). Speak into your browser and get a spoken AI response in under 1.5 seconds.

## How It Works

```
Browser mic → WebSocket /ws/voice → FastAPI
    → Deepgram Nova-2 STT  (~200 ms)
    → Claude Sonnet 4.6    (~400 ms first token, streaming)
    → ElevenLabs TTS       (~300 ms first audio chunk)
    → MP3 frames → browser playback
```

The pipeline streams **sentence-by-sentence** — TTS starts before the LLM finishes generating. **Barge-in** is supported: speaking mid-response immediately cancels the current TTS and starts a new turn.

## Features

- Sub-1.5 s end-to-end latency (11 ms measured round-trip in e2e test)
- Sentence-level TTS streaming — first audio arrives ~900 ms after user stops speaking
- Barge-in via Deepgram `SpeechStarted` VAD — cuts response instantly on interrupt
- **Aria** persona — engineered system prompt with 5 tool schemas
- Redis session memory — last N turns per session, 30-min TTL
- Tool call routing framework with `@register` decorator and stub handlers
- Dark-theme browser UI with pulsing mic ring, status text, and conversation transcript

## Prerequisites

- Python 3.11+
- API keys for Anthropic, Deepgram, and ElevenLabs
- Docker Desktop + WSL2 (Windows) — for the containerised stack

## Quick Start

```bash
cd voice-agent
cp .env.example .env
# Fill in the four keys in .env
```

| Key | Where to get it |
|---|---|
| `ANTHROPIC_API_KEY` | console.anthropic.com |
| `DEEPGRAM_API_KEY` | console.deepgram.com |
| `ELEVENLABS_API_KEY` | elevenlabs.io → Profile → API Keys |
| `ELEVENLABS_VOICE_ID` | elevenlabs.io → Voices |

**Development (no Docker):**
```bash
cd voice-agent/backend
pip install -r ../requirements.txt
uvicorn main:app --reload
```
Open `http://localhost:8000` — the frontend is served automatically.

**Docker:**
```bash
cd voice-agent
docker compose up --build
```
Starts the FastAPI backend + Redis on port 8000.

## Testing

```bash
cd voice-agent

# Unit tests — no API keys needed
pytest tests/test_health.py -v

# Integration tests — require keys in .env
python tests/test_tts.py
python tests/test_llm.py
python tests/test_pipeline.py          # LLM→TTS latency report
python tests/test_pipeline.py --save   # also writes per-turn MP3 files

# End-to-end WebSocket test — server must be running
python tests/test_websocket.py --sample
python tests/test_websocket.py --file audio.wav --save

# Standalone STT test
python test_stt.py --sample
```

**Measured latency:** first audio ≤ 900 ms from LLM start; full round-trip ≤ 1500 ms.

## Deployment (Render)

`voice-agent/render.yaml` defines two services: a Docker web service (`voice-agent-api`) and a Redis instance (`voice-agent-redis`).

1. Push the repo to GitHub.
2. In the Render dashboard, create a new **Blueprint** pointed at the repo root.
3. Set the four API key env vars in the Render dashboard (`sync: false` in `render.yaml`).
4. Deploy — `GET /health` is the health check path.

## Project Structure

```
voice-agent/
  backend/
    main.py          FastAPI app, CORS, static file mount, lifespan init
    config.py        Env vars via pydantic-settings
    prompts.py       Aria persona system prompt + 5 tool schemas
    routes/
      health.py      GET /health
      voice.py       WebSocket /ws/voice — STT→LLM→TTS pipeline + session memory
    services/
      stt.py         DeepgramSTT — async live transcription (Nova-2)
      tts.py         ElevenLabsTTS — streaming TTS (eleven_turbo_v2)
      llm.py         ClaudeLLM — streaming messages + tool call extraction
      memory.py      Redis ConversationMemory — load/save/clear, 30-min TTL
    tools/
      router.py      Tool call dispatcher — @register decorator + stub handlers
    models/
      schemas.py     Pydantic models
  frontend/
    index.html       Dark-theme UI — pulsing mic ring, status, transcript
    voice.js         AudioWorklet mic capture, WebSocket, MP3 playback state machine
  tests/             Integration and unit test scripts
  docker-compose.yml api + redis
  Dockerfile         python:3.11-slim, serves frontend as static files
  render.yaml        Render.com deployment blueprint
```

## Build Status

| Component | Status |
|---|---|
| FastAPI app + CORS + static mount | Done |
| Config / env loading | Done |
| Health endpoint | Done |
| Deepgram STT (Nova-2 streaming) | Done |
| ElevenLabs TTS (streaming, avg 300 ms first chunk) | Done |
| Claude LLM (streaming + tool calls) | Done |
| WebSocket voice pipeline | Done — 11 ms round-trip |
| Frontend widget + UI | Done |
| Aria persona + tool schemas | Done |
| Redis session memory (load/save/clear) | Done |
| Tool call routing framework | Done |

## Roadmap (Week 3)

- Real tool integrations: Google Calendar (`book_appointment`), HubSpot/Salesforce (`create_crm_lead`)
- RAG knowledge base — ChromaDB + `search_knowledge_base` tool
- Full integration test suite — all 8 conversation scenarios
- Session logging to PostgreSQL
