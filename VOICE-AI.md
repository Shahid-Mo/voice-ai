# Voice AI - Project Vision

## Mission

Build a comprehensive, modular Voice AI platform that demonstrates mastery across the entire voice AI stack. This is not a single demo - it's a **playground for testing, comparing, and understanding every component** in the voice AI ecosystem.

**Goal:** Become an authority on all things Voice AI.

---

## The Modular Architecture

Every component is **swappable**. No vendor lock-in. Test everything.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                                USER (Bob)                                    │
│                              Speaks into phone                               │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        PSTN → Internet Gateway                               │
│  ┌─────────┐  ┌─────────┐  ┌─────────────┐  ┌─────────┐                    │
│  │  VAPI   │  │ Twilio  │  │   Telnyx    │  │SignalWire│                   │
│  │ (free#) │  │         │  │             │  │         │                    │
│  └─────────┘  └─────────┘  └─────────────┘  └─────────┘                    │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           STT (Speech-to-Text)                               │
│  ┌───────────┐  ┌─────────────┐  ┌──────────┐  ┌──────────┐                │
│  │ Deepgram  │  │ AssemblyAI  │  │  Whisper │  │  Google  │                │
│  │           │  │             │  │  (local) │  │   STT    │                │
│  └───────────┘  └─────────────┘  └──────────┘  └──────────┘                │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              LLM (Brain)                                     │
│  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌───────────┐                │
│  │   Groq    │  │  OpenAI   │  │  Gemini   │  │  Claude   │                │
│  │  (Llama)  │  │  GPT-4o   │  │           │  │           │                │
│  └───────────┘  └───────────┘  └───────────┘  └───────────┘                │
│                          │                                                   │
│            ┌─────────────┴─────────────┐                                    │
│            ▼                           ▼                                    │
│   ┌─────────────────┐        ┌─────────────────┐                           │
│   │  RAG Retrieval  │        │  Function Call  │                           │
│   │  (Knowledge)    │        │  (Actions/DB)   │                           │
│   └─────────────────┘        └─────────────────┘                           │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           TTS (Text-to-Speech)                               │
│  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌───────────┐                │
│  │ Cartesia  │  │ Deepgram  │  │ ElevenLabs│  │  PlayHT   │                │
│  │           │  │    TTS    │  │           │  │           │                │
│  └───────────┘  └───────────┘  └───────────┘  └───────────┘                │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Data Layer                                      │
│  ┌─────────────────────────────┐  ┌─────────────────────────────┐          │
│  │       Vector Store          │  │       Relational DB         │          │
│  │  ┌─────────┐ ┌──────────┐  │  │  ┌─────────┐ ┌──────────┐  │          │
│  │  │PgVector │ │ Pinecone │  │  │  │PostgreSQL│ │  SQLite  │  │          │
│  │  └─────────┘ └──────────┘  │  │  └─────────┘ └──────────┘  │          │
│  │  ┌─────────┐ ┌──────────┐  │  │                             │          │
│  │  │ Qdrant  │ │ Chroma   │  │  │                             │          │
│  │  └─────────┘ └──────────┘  │  │                             │          │
│  └─────────────────────────────┘  └─────────────────────────────┘          │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Voice AI Use Cases to Implement

### Phase 1: Foundation Use Cases

| Use Case | Description | Components Tested |
|----------|-------------|-------------------|
| **Simple Q&A** | Answer questions from knowledge base | STT → LLM → RAG → TTS |
| **Phone Survey** | Ask questions, record answers to DB | STT → LLM → DB Write → TTS |
| **Booking Agent** | Book appointments, check availability | STT → LLM → Function Calling → DB → TTS |

### Phase 2: Advanced Use Cases

| Use Case | Description | Components Tested |
|----------|-------------|-------------------|
| **Customer Support** | Handle support tickets, escalate when needed | Full pipeline + routing logic |
| **Outbound Calling** | Proactive calls (reminders, confirmations) | Reverse flow initiation |
| **Multi-turn Conversations** | Complex dialogues with context | Conversation state management |
| **Handoff to Human** | Detect frustration, transfer to agent | Sentiment + routing |

### Phase 3: Native Voice Models

| Use Case | Description | Components Tested |
|----------|-------------|-------------------|
| **OpenAI Realtime API** | Direct speech-to-speech | Compare latency, quality |
| **Gemini Live** | Google's native voice | Compare capabilities |
| **Ultravox/Moshi** | Open source alternatives | Self-hosted options |

---

## Provider Comparison Matrix

### STT Providers

| Provider | Free Tier | Latency | Accuracy | Notes |
|----------|-----------|---------|----------|-------|
| Deepgram | $200 credits | Very Low | High | Best for real-time |
| AssemblyAI | $50 credits | Low | High | Good accuracy |
| Whisper (local) | Free | Medium | High | Self-hosted option |
| Google STT | $300 GCP | Low | High | Enterprise option |

### LLM Providers

| Provider | Free Tier | Latency | Function Calling | Notes |
|----------|-----------|---------|------------------|-------|
| Groq (Llama) | Free tier | Very Low | Yes | Fastest inference |
| OpenAI GPT-4o | Pay as you go | Low | Excellent | Best function calling |
| Gemini | Free tier | Low | Yes | Good free tier |
| Claude | Pay as you go | Low | Yes | Best reasoning |

### TTS Providers

| Provider | Free Tier | Latency | Quality | Notes |
|----------|-----------|---------|---------|-------|
| Cartesia | Free tier | Very Low | High | Optimized for real-time |
| Deepgram TTS | Included | Very Low | Good | Same provider as STT |
| ElevenLabs | Limited free | Medium | Excellent | Best voice quality |
| PlayHT | Free tier | Medium | High | Good customization |

### Phone/PSTN Providers

| Provider | Free Tier | Ease of Setup | Notes |
|----------|-----------|---------------|-------|
| VAPI | $10 credits + free number | One-click | Best for quick start |
| Twilio | Trial credits | Medium | Industry standard |
| Telnyx | Pay as you go | Medium | Good rates |
| SignalWire | Free tier | Medium | Twilio alternative |

### Vector DB Providers

| Provider | Free Tier | Self-Host | Notes |
|----------|-----------|-----------|-------|
| PgVector | Free (PostgreSQL extension) | Yes | Use existing Postgres |
| Pinecone | Free tier | No | Managed, easy |
| Qdrant | 1GB free cloud | Yes | Good balance |
| Chroma | Free (local) | Yes | Simple, local-first |

---

## Deployment Strategies to Demonstrate

### Strategy 1: Single EC2 (Learning)
- Everything on one box
- Caddy for HTTPS
- Good for understanding fundamentals
- Cost: ~$0 (free tier)

### Strategy 2: Managed Services
- RDS for PostgreSQL
- Managed vector DB (Pinecone/Qdrant Cloud)
- EC2 for application only
- Cost: ~$20-50/month

### Strategy 3: Container-Based (Fargate)
- Dockerized application
- ECS + Fargate
- Auto-scaling
- Cost: Pay per use

### Strategy 4: Serverless (Lambda)
- For simpler use cases
- API Gateway + Lambda
- Cold start considerations
- Cost: Very low for low traffic

### Strategy 5: Self-Hosted Everything
- EC2 with local Whisper
- Local LLM (Ollama)
- PgVector in PostgreSQL
- Cost: Fixed EC2 cost, no API fees

---

## Dataset: Bitext Customer Support

**Source:** `bitext/Bitext-customer-support-llm-chatbot-training-dataset` (HuggingFace)

**Why this dataset:**
- Real customer support conversations
- Multiple intents and categories
- Good for testing RAG retrieval
- Can simulate realistic scenarios

**Use cases:**
- RAG knowledge base
- Intent classification testing
- Response quality benchmarking

---

## Content Roadmap (YouTube Series)

### Video 1: Foundation
- Project setup
- Modular architecture explanation
- First working call (STT → LLM → TTS)
- VAPI for phone number

### Video 2: RAG Deep Dive
- Vector databases compared
- Bitext dataset ingestion
- Retrieval strategies
- When RAG fails

### Video 3: Actions & DB Writes
- Function calling explained
- Phone survey implementation
- Booking system
- DB update patterns

### Video 4: Provider Shootout
- STT comparison (Deepgram vs AssemblyAI)
- TTS comparison (Cartesia vs ElevenLabs)
- LLM comparison for voice (latency matters)
- Cost analysis

### Video 5: Deployment Deep Dive
- EC2 from scratch
- Fargate scaling
- Monitoring & logging
- Production checklist

### Video 6: Native Voice Models
- OpenAI Realtime API
- Gemini Live
- When to use what
- Future of voice AI

---

## Success Metrics

1. **Working demos** for each use case
2. **Benchmark data** for each provider comparison
3. **Cost tracking** across all approaches
4. **Latency measurements** for full pipeline
5. **Code quality** - production-grade, not tutorial garbage
6. **Educational value** - viewers can replicate everything

---

## Non-Goals (For Now)

- Building custom STT/TTS models
- Mobile app development
- Multi-language support (focus on English first)
- Enterprise features (SSO, audit logs, etc.)

---

## Tech Stack Summary

| Layer | Primary Choice | Alternatives to Test |
|-------|---------------|---------------------|
| Language | Python 3.11+ | - |
| Framework | FastAPI | - |
| Phone | VAPI (free number) | Twilio, Telnyx, SignalWire |
| STT | Deepgram | AssemblyAI, Whisper |
| LLM | Groq (Llama) | OpenAI, Gemini, Claude |
| TTS | Cartesia | Deepgram, ElevenLabs |
| Vector DB | PgVector | Pinecone, Qdrant |
| Relational DB | PostgreSQL | SQLite (local dev) |
| Deployment | AWS EC2 | Fargate, Lambda |
| Reverse Proxy | Caddy | nginx |

---

## Next Steps

1. Create project structure with pluggable providers
2. Implement provider interfaces (STT, LLM, TTS, VectorDB)
3. Build first use case: Simple Q&A with RAG
4. Add second use case: Phone survey with DB write
5. Add third use case: Booking agent
6. Deploy to AWS
7. Record video
8. Iterate based on feedback
