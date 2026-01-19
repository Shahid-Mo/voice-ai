# CLAUDE.md - Voice AI Project Guide

## Project Overview

A modular Voice AI platform with **pluggable providers** for every component. The goal is to build a comprehensive system that can swap STT, LLM, TTS, and VectorDB providers without code changes.

**Mission:** Become an authority on all things Voice AI by testing, comparing, and understanding every component in the ecosystem.

## Tech Stack

- **Language:** Python 3.12+
- **Framework:** FastAPI + uvicorn
- **Config:** pydantic-settings (auto-loads `.env`)
- **Primary Providers:** Deepgram (STT/TTS), OpenAI (LLM)
- **Package Manager:** uv

## Project Structure

```
src/voice_ai/
├── main.py              # FastAPI entry point
├── config.py            # Settings (pydantic-settings)
├── providers/           # Pluggable provider system
│   ├── stt/             # Speech-to-Text
│   │   ├── base.py      # STTProvider interface
│   │   └── deepgram.py  # Deepgram Flux implementation
│   ├── llm/             # Language Models
│   │   └── base.py      # LLMProvider interface
│   └── tts/             # Text-to-Speech
│       ├── base.py      # TTSProvider interface
│       └── deepgram.py  # Deepgram Aura implementation
├── services/            # Business logic & orchestration
├── api/routes/          # HTTP endpoints (thin layer)
│   └── health.py        # Health check endpoints
└── models/              # Pydantic schemas
```

## Architecture: Routes vs Services vs Providers

```
Routes (api/) → Services (services/) → Providers (providers/)
   │                  │                      │
   └─ HTTP only       └─ Business logic      └─ External APIs
```

- **Routes:** Handle HTTP requests/responses only. No business logic.
- **Services:** Orchestrate flows (STT → LLM → TTS). Business rules.
- **Providers:** Talk to external APIs. Implement interfaces. Swappable.

## Commands

```bash
# Run the server
uv run uvicorn voice_ai.main:app --reload

# Or directly
uv run python -m voice_ai.main

# Run tests
uv run pytest

# Type checking
uv run mypy src/

# Linting
uv run ruff check src/
uv run ruff format src/
```

## Environment Variables

Copy `.env.example` to `.env` and fill in API keys:

```bash
STT_PROVIDER=deepgram
LLM_PROVIDER=openai
TTS_PROVIDER=deepgram

DEEPGRAM_API_KEY=your_key_here
OPENAI_API_KEY=your_key_here

HOST=0.0.0.0
PORT=8000
DEBUG=true
```

## Provider Interfaces

### STT (Speech-to-Text)
- `transcribe(audio_data: bytes) -> STTEvent` - Batch transcription
- `connect(on_event, sample_rate, encoding)` - Open streaming connection
- `send_audio(audio_chunk: bytes)` - Send audio to stream
- `close()` - Close connection

**Deepgram Flux features:** EndOfTurn, EagerEndOfTurn, TurnResumed events for intelligent turn detection.

### LLM
- `complete(messages, tools) -> LLMResponse` - Generate completion
- `stream_complete(messages) -> AsyncIterator[str]` - Stream completion

### TTS (Text-to-Speech)
- `synthesize(text, voice) -> TTSResult` - Convert text to audio
- `synthesize_stream(text, voice) -> AsyncIterator[bytes]` - Stream audio

## Implementation Status

### Done
- [x] Project structure with `src/` layout
- [x] Config management (pydantic-settings)
- [x] FastAPI skeleton with health endpoints
- [x] STT interface + Deepgram Flux implementation
- [x] LLM interface (base only)
- [x] TTS interface + Deepgram Aura implementation

### Next
- [ ] OpenAI LLM provider implementation
- [ ] Voice orchestrator service (STT → LLM → TTS pipeline)
- [ ] VectorDB interface + PgVector implementation
- [ ] RAG service
- [ ] Phone/PSTN gateway integration (VAPI/Twilio)
- [ ] Benchmark scripts for provider comparison

## Key Design Decisions

1. **Abstract interfaces for everything** - Every provider implements a base interface. Swap Deepgram for AssemblyAI by changing one config value.

2. **Async-first** - All provider methods are async for non-blocking I/O.

3. **Event-based STT streaming** - `STTEvent` with types: TRANSCRIPT, END_OF_TURN, EAGER_END_OF_TURN, TURN_RESUMED, CONNECTED, ERROR, CLOSED.

4. **Config from environment** - `pydantic-settings` auto-loads `.env`, validates types, and provides typed access via `settings.deepgram_api_key`.

## Use Cases to Implement

1. **Simple Q&A** - Answer questions from knowledge base (STT → LLM → RAG → TTS)
2. **Phone Survey** - Ask questions, record answers to DB
3. **Booking Agent** - Book appointments, check availability

## Reference Docs

- `VOICE-AI.md` - High-level vision and provider comparison
- `PLAN.md` - Detailed implementation phases
- `shahid/skeleton/` - Architecture explanations
- `shahid/data/` - Data flow and multi-tenant RAG design
