# CLAUDE.md - Voice AI Project Guide

## Project Overview

A modular Voice AI platform with **pluggable providers** for STT, LLM, TTS, and VectorDB components. Built with 100% async architecture for real-time voice conversations.

## Quick Start

```bash
# Install dependencies
uv sync

# Run server
uv run uvicorn voice_ai.main:app --reload

# Run tests
uv run pytest

# Type checking & linting
uv run mypy src/
uv run ruff check src/
```

## Architecture

### 100% Async - No Threading

- All code uses `async`/`await` - no `threading`, no `ThreadPoolExecutor`
- Native async clients: `AsyncDeepgramClient`, async OpenAI SDK
- Proven pattern: see `tests/test_async_deepgram.py`

### Layer Structure

```
Routes (api/routes/) → Services (services/) → Providers (providers/)
   │                       │                        │
   └─ HTTP only            └─ Business logic        └─ External APIs
```

### Project Structure

```
src/voice_ai/
├── main.py              # FastAPI entry point
├── config.py            # Pydantic settings
├── audio_utils.py       # μ-law/PCM conversion
├── api/routes/          # HTTP/WebSocket endpoints
│   ├── health.py        # Health checks
│   └── voice_ws.py      # Twilio WebSocket
├── services/
│   └── voice_session.py # STT→LLM→TTS orchestrator
└── providers/
    ├── stt/deepgram.py  # Deepgram Flux STT
    ├── llm/openai.py    # OpenAI Responses API
    └── tts/deepgram.py  # Deepgram Aura TTS
```

## Environment Setup

Copy `.env.example` to `.env`:

```bash
DEEPGRAM_API_KEY=your_key
OPENAI_API_KEY=your_key
HOST=0.0.0.0
PORT=8000
DEBUG=true
```

## Provider Interfaces

### STT (Speech-to-Text)
- `transcribe_stream(audio, callback)` - Streaming with turn detection
- Events: `EndOfTurn`, `EagerEndOfTurn`, `TurnResumed`

### LLM
- `stream_complete(messages, conversation_id)` - Streaming responses
- Uses OpenAI Responses API for automatic conversation state

### TTS (Text-to-Speech)
- `synthesize_stream(text)` - Streaming audio synthesis
- Sentence-by-sentence for low latency

## Key Design Decisions

1. **100% Async** - Proven in `tests/test_async_deepgram.py`
2. **Persistent STT** - Connection stays open for entire call
3. **Sentence Streaming** - Buffer LLM until `.!?`, then TTS immediately
4. **PCM 16kHz Internal** - All endpoints convert to/from this format

## Documentation

| Doc | Purpose |
|-----|---------|
| `VOICE-AI.md` | High-level vision, provider comparison |
| `docs/ARCHITECTURE.md` | System design details |
| `docs/CODE_GUIDE.md` | Key files explained |
| `docs/JOURNEY.md` | Lessons learned, pitfalls |

## Deployment

Development:
```bash
uv run uvicorn voice_ai.main:app --reload
```

Production (see `infra/`):
- Docker: `docker-compose up`
- AWS: EC2/Fargate configs in `infra/aws/`
