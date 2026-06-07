# AI Voice Agent

A real-time browser-based voice agent powered by Deepgram (STT), Claude Sonnet 4.6 (LLM), and ElevenLabs (TTS). Speak into your browser, get a spoken AI response in under 1.5 seconds.

## How It Works

```
Browser mic → WebSocket → FastAPI
    → Deepgram Nova-2 STT  (~200 ms)
    → Claude Sonnet 4.6    (~400 ms first token)
    → ElevenLabs TTS       (~300 ms first audio)
    → MP3 frames → browser playback
```

The pipeline streams sentence-by-sentence — TTS starts before the LLM finishes. Barge-in is supported: speaking mid-response cancels the current TTS immediately.

## Prerequisites

- Python 3.11+
- API keys for Anthropic, Deepgram, and ElevenLabs
- Docker Desktop + WSL2 (Windows) — for the containerised stack only

## Setup

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

## Running

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
python tests/test_websocket.py --sample        # downloads a sample wav
python tests/test_websocket.py --file audio.wav --save

# Standalone STT test
python test_stt.py --sample
```

**Latency targets:** first audio ≤ 900 ms from LLM start; full round-trip ≤ 1500 ms.

## Deployment (Render)

`voice-agent/render.yaml` defines two services: a Docker web service (`voice-agent-api`) and a Redis instance (`voice-agent-redis`). To deploy:

1. Push the repo to GitHub.
2. In the Render dashboard, create a new Blueprint and point it at the repo root.
3. Set the four API key env vars in the Render dashboard (they are marked `sync: false` in `render.yaml`).
4. Deploy — `GET /health` is the health check path.

## Project Structure

```
voice-agent/
  backend/
    main.py          FastAPI app, CORS, static file mount
    config.py        Env vars via pydantic-settings
    prompts.py       System prompt + tool schemas
    routes/
      health.py      GET /health
      voice.py       WebSocket /ws/voice — full STT→LLM→TTS pipeline
    services/
      stt.py         DeepgramSTT — async live transcription wrapper
      tts.py         ElevenLabsTTS — streaming TTS wrapper
      llm.py         ClaudeLLM — streaming messages + tool call extraction
      memory.py      Redis session memory (Week 2)
    tools/
      router.py      Tool call dispatcher (Week 2)
  frontend/
    index.html       Dark-theme UI with pulsing mic ring + transcript
    voice.js         AudioWorklet mic capture, WebSocket, MP3 playback
  tests/             Integration and unit test scripts
  docker-compose.yml api + redis
  Dockerfile         python:3.11-slim, serves frontend as static files
  render.yaml        Render.com deployment blueprint
```

## Roadmap (Week 2)

- Redis session memory (`services/memory.py`) — last N turns per session, 30-min TTL
- Agent persona + engineered system prompt (`prompts.py`)
- Tool call routing framework (`tools/router.py`) → Calendar, CRM, knowledge base integrations
- Full integration test suite (8 scenarios)
