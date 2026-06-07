# AI Voice Agent — Detailed Project Plan

## Executive Summary

Build a real-time, low-latency AI voice agent capable of natural conversation, intent detection, business logic execution, and integration with external systems (CRM, calendar, databases). The MVP is delivered in ~4 weeks; post-MVP enhancements follow.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     USER CHANNELS                           │
│         Web Browser │ Phone Call │ WhatsApp / Mobile        │
└────────────┬─────────────┬──────────────┬───────────────────┘
             │             │              │
        WebRTC/WS     Twilio Voice    Twilio API
             │             │              │
             └──────────────┴──────────────┘
                            │
                    ┌───────▼────────┐
                    │  Audio Gateway │  (LiveKit / Twilio Media Stream)
                    │  WebRTC Server │
                    └───────┬────────┘
                            │ Raw audio stream
                    ┌───────▼────────┐
                    │  STT Engine    │  Deepgram Nova-2 (streaming)
                    │  (real-time)   │  ~200ms latency
                    └───────┬────────┘
                            │ Transcribed text + timestamps
                    ┌───────▼────────┐
                    │  Conversation  │  Turn management
                    │  Orchestrator  │  Interruption handling
                    │  (FastAPI)     │  VAD (voice activity detection)
                    └───────┬────────┘
                            │ Text + conversation history
              ┌─────────────▼──────────────────────┐
              │         LLM Engine                  │
              │  Claude Sonnet 4.6 / GPT-4o         │
              │  - Intent detection                  │
              │  - Response generation               │
              │  - Tool/function calling             │
              └──────┬──────────────────────────────┘
                     │ Tool calls / actions
         ┌───────────▼───────────────────────────────┐
         │          Business Logic Layer              │
         │  ┌──────────┐  ┌──────────┐  ┌─────────┐  │
         │  │  CRM API  │  │Calendar  │  │   RAG   │  │
         │  │HubSpot/SF │  │ Google   │  │Knowledge│  │
         │  └──────────┘  └──────────┘  └─────────┘  │
         │  ┌──────────┐  ┌──────────┐               │
         │  │ Database  │  │  Custom  │               │
         │  │PostgreSQL │  │   APIs   │               │
         │  └──────────┘  └──────────┘               │
         └───────────────────────────────────────────┘
                     │ LLM text response
                    ┌▼────────────────┐
                    │   TTS Engine    │  ElevenLabs / OpenAI TTS
                    │  (streaming)    │  ~300ms first-byte latency
                    └───────┬─────────┘
                            │ Audio stream
                    ┌───────▼─────────┐
                    │  User Channel   │  Audio back to user
                    └─────────────────┘

         ┌─────────────────────────────────────────┐
         │           Memory & State Layer           │
         │  Redis: short-term session context       │
         │  PostgreSQL: long-term conversation logs │
         │  Pinecone/Chroma: vector embeddings      │
         └─────────────────────────────────────────┘
```

---

## Technology Stack

### Option A — Vapi.ai Managed Platform (Recommended for MVP Speed)

| Layer | Tool | Reason |
|---|---|---|
| Voice Orchestration | **Vapi.ai** | Handles STT+LLM+TTS pipeline, built-in WebRTC, phone, and web widget |
| LLM | Claude Sonnet 4.6 or GPT-4o | Best instruction-following, function calling |
| TTS | ElevenLabs (via Vapi) | Most natural voice, low latency |
| STT | Deepgram (via Vapi) | Best accuracy, streaming transcription |
| Backend | FastAPI (Python) | Handles Vapi webhooks, tool calls, business logic |
| Memory | Redis + PostgreSQL | Session context + persistent logs |
| Phone | Twilio (via Vapi) | Phone number provisioning |
| Deployment | Docker on AWS/GCP | Containerized, scalable |

**Why Vapi:** Manages the hard real-time audio infrastructure, phone integration, and voice pipeline — reducing MVP time from 6 weeks to 3 weeks. Custom logic is added via webhook tool calls.

---

### Option B — Custom Full Stack (More Control)

| Layer | Tool | Reason |
|---|---|---|
| Real-time Audio | **LiveKit** | Open-source WebRTC, low latency, self-hostable |
| STT | **Deepgram Nova-2** | Streaming, <200ms, high accuracy |
| LLM | **Claude Sonnet 4.6** | Best conversational quality and tool use |
| TTS | **ElevenLabs** (streaming) | Near-human voice, 300ms first byte |
| Backend | **FastAPI** | Async Python, handles concurrency well |
| Conversation Memory | **Redis** (session) | Sub-ms read/write for context management |
| Long-term Memory | **PostgreSQL** | Stores conversation history, user profiles |
| RAG / Knowledge Base | **ChromaDB** (local) or **Pinecone** (cloud) | Business-specific knowledge retrieval |
| Phone Integration | **Twilio Voice** | Programmable calls, SIP |
| WhatsApp | **Twilio WhatsApp API** | Send/receive audio messages |
| Deployment | **Docker + AWS ECS** | Containerized microservices |
| Monitoring | **Prometheus + Grafana** | Latency and usage tracking |

---

## System Components In Detail

### 1. Audio Gateway (Real-time Audio Handling)
- Accepts WebRTC or phone audio stream
- Applies Voice Activity Detection (VAD) to detect speech start/end
- Handles user interruptions mid-response (barge-in detection)
- Buffers audio chunks and sends to STT

### 2. Speech-to-Text (STT)
- **Deepgram Nova-2** streaming endpoint
- Outputs partial + final transcriptions
- ~150–200ms word-level latency
- Language detection support

### 3. Conversation Orchestrator (FastAPI)
- Maintains conversation state per session
- Tracks turn history (last N exchanges in Redis)
- Detects conversation intent from transcript
- Routes to LLM with injected system prompt + memory
- Handles concurrent sessions

### 4. LLM Engine
- **Claude Sonnet 4.6** (or GPT-4o as fallback)
- System prompt: defines agent persona, capabilities, limitations
- Tool/function definitions: CRM lookup, calendar booking, FAQ retrieval
- Streaming responses: first token in ~500ms
- Response is chunked and sent to TTS as sentences complete

### 5. Business Logic & Integrations
- **Tool Call Router**: maps LLM tool calls to actual API calls
- Built-in tools at MVP:
  - `search_knowledge_base(query)` — RAG over uploaded docs
  - `book_appointment(date, time, name, email)` — Google Calendar
  - `create_crm_lead(name, email, phone, notes)` — HubSpot/Salesforce
  - `lookup_customer(phone_or_email)` — CRM record fetch
  - `send_followup_email(to, summary)` — SendGrid/Gmail

### 6. Text-to-Speech (TTS)
- **ElevenLabs Streaming API** — sentence-level streaming
- Voice cloning option for brand voice
- First audio chunk delivered in ~300ms after text generation starts
- Fallback: OpenAI TTS (lower cost, slightly less natural)

### 7. Memory Layer
- **Redis**: active session context (last 10 turns), TTL 30 min
- **PostgreSQL**: full conversation history, user profiles, analytics
- **Vector DB (Chroma/Pinecone)**: embedded documents for RAG
  - FAQs, product docs, pricing sheets, SOPs

---

## Conversation Flow Design

```
[User speaks]
      │
      ▼
VAD detects speech end (silence ~500ms)
      │
      ▼
Audio → Deepgram → transcript
      │
      ▼
Orchestrator: inject context + history into LLM prompt
      │
      ▼
LLM processes → decides: respond directly OR call a tool
      │
      ├── TOOL CALL → execute API → inject result → LLM generates response
      │
      └── DIRECT RESPONSE → stream text to TTS
                │
                ▼
          ElevenLabs → audio stream → user hears response
                │
                ▼
          Update Redis context, log to PostgreSQL
```

### Barge-In Handling
- If user speaks while agent is responding, audio stream is cut
- Partial response discarded, new transcription processed immediately
- Prevents robotic "wait for me to finish" behavior

### Intent Categories (MVP)
| Intent | Action |
|---|---|
| Greeting / small talk | Direct LLM response |
| Product / service question | RAG knowledge base lookup |
| Book appointment | Calendar API |
| Get pricing / quote | Knowledge base + CRM lookup |
| Speak to human | Handoff trigger (notify agent, end call) |
| Complaint / issue | CRM ticket creation |
| Goodbye / end call | Graceful close, send follow-up |

---

## Deployment Architecture

```
┌─────────────────────────────────────────┐
│              AWS / GCP                  │
│                                         │
│  ┌─────────────┐  ┌─────────────────┐   │
│  │  FastAPI    │  │  Redis (cache)  │   │
│  │  (ECS/K8s)  │  │  (ElastiCache)  │   │
│  └──────┬──────┘  └─────────────────┘   │
│         │                               │
│  ┌──────▼──────┐  ┌─────────────────┐   │
│  │ PostgreSQL  │  │  Chroma/Pinecone │   │
│  │  (RDS)      │  │  (vector store) │   │
│  └─────────────┘  └─────────────────┘   │
│                                         │
│  ┌──────────────────────────────────┐   │
│  │  Nginx / Load Balancer           │   │
│  └──────────────────────────────────┘   │
└─────────────────────────────────────────┘

External APIs: Deepgram, ElevenLabs, Claude/OpenAI,
               Twilio, HubSpot, Google Calendar
```

- Docker containers for all services
- Environment variables via AWS Secrets Manager
- Auto-scaling based on concurrent sessions
- WebSocket connections for real-time audio

---

## Project Phases & Timeline

### Phase 1 — MVP (Weeks 1–4)

**Week 1: Infrastructure & Pipeline**
- [ ] Set up FastAPI backend + Docker
- [ ] Integrate Deepgram STT (streaming)
- [ ] Integrate ElevenLabs TTS (streaming)
- [ ] Connect Claude Sonnet 4.6 as LLM
- [ ] Build basic audio WebSocket endpoint
- [ ] Test end-to-end voice loop (speak → respond)

**Week 2: Conversation Logic**
- [ ] System prompt design and agent persona
- [ ] Redis session memory (last N turns)
- [ ] VAD + barge-in interrupt handling
- [ ] Intent detection via LLM function calling
- [ ] Basic tool call routing framework

**Week 3: First Integration**
- [ ] Choose primary integration (Google Calendar OR HubSpot CRM)
- [ ] Build tool: `book_appointment()` or `create_lead()`
- [ ] Basic RAG knowledge base (ChromaDB + uploaded docs)
- [ ] `search_knowledge_base()` tool
- [ ] Conversation flow testing

**Week 4: Testing & Web Deployment**
- [ ] Web-based voice widget (HTML/JS, WebRTC)
- [ ] End-to-end latency optimization (<1.5s target)
- [ ] Session logging to PostgreSQL
- [ ] Bug fixes and conversation quality pass
- [ ] Docker deployment to AWS/GCP
- [ ] Documentation (setup guide, API docs, prompt guide)

**MVP Deliverable**: Working web voice agent with one integration, sub-1.5s latency, deployed and accessible via URL.

---

### Phase 2 — Enhancement (Weeks 5–7)

- [ ] Phone call support via Twilio Voice
- [ ] Additional CRM or calendar integrations
- [ ] Human handoff / escalation flow
- [ ] Persistent user memory (returning caller recognition)
- [ ] WhatsApp voice note support
- [ ] Prompt engineering refinement (edge case handling)
- [ ] Analytics dashboard (calls, intents, resolution rate)
- [ ] Voice persona customization (ElevenLabs voice cloning)

---

### Phase 3 — Scale & Optimize (Weeks 8–9)

- [ ] Load testing (concurrent session handling)
- [ ] Latency optimization (streaming pipeline tuning)
- [ ] Monitoring: Prometheus + Grafana dashboards
- [ ] Multi-language support (if needed)
- [ ] Admin panel for managing knowledge base
- [ ] Production hardening (auth, rate limits, error recovery)

---

## Latency Budget (Target: <1.5s end-to-end)

| Stage | Target Latency |
|---|---|
| VAD silence detection | ~400ms |
| Deepgram STT (streaming final) | ~200ms |
| Network + orchestrator processing | ~50ms |
| LLM first token (Claude streaming) | ~400ms |
| ElevenLabs TTS first audio chunk | ~300ms |
| Network to client | ~50ms |
| **Total** | **~1.4s** |

Optimizations:
- Start TTS as each sentence completes (don't wait for full LLM response)
- Pre-warm LLM with system prompt (reduce cold start)
- Redis for context (no DB read on every turn)
- CDN for audio delivery

---

## Cost Estimates (Monthly, Production)

| Service | Usage | Cost/mo |
|---|---|---|
| Deepgram Nova-2 | 1,000 min/mo | ~$50 |
| ElevenLabs (streaming) | 1,000 min/mo | ~$100 |
| Claude Sonnet 4.6 | ~2M tokens/mo | ~$60 |
| Twilio Voice | 500 min/mo | ~$40 |
| AWS (ECS + RDS + Redis) | Medium instance | ~$120 |
| Pinecone / ChromaDB | Standard | ~$25 |
| **Total** | | **~$395/mo** |

---

## Project Budget & Timeline Summary

| Phase | Duration | Deliverables | Est. Cost |
|---|---|---|---|
| MVP | 4 weeks | Working voice agent, 1 integration, web deploy | $4,000–$5,500 |
| Enhancement | 3 weeks | Phone, WhatsApp, 2+ integrations, analytics | $2,500–$3,500 |
| Scale & Optimize | 2 weeks | Load-tested, monitored, production-ready | $1,500–$2,000 |
| **Total** | **9 weeks** | | **$8,000–$11,000** |

Hourly rate alternative: **$65–$85/hr**

---

## Risk Factors & Mitigations

| Risk | Mitigation |
|---|---|
| Latency exceeds 2s | Use Vapi.ai as orchestrator (pre-built pipeline) |
| STT accuracy on domain terms | Custom vocabulary / Deepgram keyword boost |
| LLM hallucinations | Constrain with strict prompts + RAG grounding |
| Twilio phone audio quality | Use codec PCMU/G711, match Deepgram settings |
| Concurrent session scaling | WebSocket pool + Redis pub/sub + horizontal scaling |
| Cost overrun on TTS | Implement caching for repeated phrases |

---

## Recommended Approach for This Client

Given the Upwork context (MVP first, business integration needed):

1. **Start with Vapi.ai** for the voice pipeline — reduces infrastructure complexity by ~60%, gets MVP live in 2–3 weeks
2. **Build custom FastAPI backend** for webhook tool calls — this is where all business logic lives and is fully owned code
3. **Use Claude Sonnet 4.6** as the LLM — best function-calling quality for tool routing
4. **First integration: Google Calendar** — universally useful, easy to demo
5. **Deliver a live URL** the client can test immediately

After MVP validation, migrate to custom LiveKit stack if the client needs more control over audio quality, on-premise hosting, or cost reduction at scale.

---

## File Structure (MVP)

```
voice-agent/
├── backend/
│   ├── main.py                  # FastAPI app entrypoint
│   ├── routes/
│   │   ├── webhook.py           # Vapi webhook handler
│   │   ├── voice.py             # WebSocket audio endpoint
│   │   └── health.py
│   ├── services/
│   │   ├── stt.py               # Deepgram client
│   │   ├── tts.py               # ElevenLabs client
│   │   ├── llm.py               # Claude/OpenAI client
│   │   ├── memory.py            # Redis session manager
│   │   └── rag.py               # ChromaDB / Pinecone queries
│   ├── tools/
│   │   ├── calendar.py          # Google Calendar integration
│   │   ├── crm.py               # HubSpot / Salesforce
│   │   ├── knowledge_base.py    # RAG search tool
│   │   └── router.py            # Tool call dispatcher
│   ├── models/
│   │   └── schemas.py           # Pydantic models
│   └── config.py                # Settings, env vars
├── frontend/
│   ├── index.html               # Web voice widget
│   └── voice.js                 # WebRTC / audio handling
├── data/
│   └── knowledge_base/          # Uploaded docs for RAG
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── .env.example
```

---

## Next Steps

1. **Confirm primary use case** — customer support, appointment booking, sales, or internal tool?
2. **Confirm first integration** — CRM (HubSpot/Salesforce), Calendar, or database?
3. **Confirm deployment channel** — web widget, phone number, or WhatsApp?
4. **Choose stack** — Vapi.ai (fast) vs. custom LiveKit (control)
5. Begin Week 1 sprint upon approval
