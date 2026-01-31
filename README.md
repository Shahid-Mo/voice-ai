# Voice AI Platform

A modular, production-grade Voice AI system with pluggable providers for STT, LLM, TTS, and VectorDB.

## Features

- **100% Async Architecture** - Native async/await throughout, no threading
- **Pluggable Providers** - Swap Deepgram, OpenAI, etc. via config
- **Real-time Streaming** - WebSocket-based voice conversations
- **Phone Integration** - Twilio Media Streams support
- **Turn Detection** - Deepgram Flux for natural conversation flow

## Quick Start

```bash
# Install
uv sync

# Configure
cp .env.example .env
# Edit .env with your API keys

# Run
uv run uvicorn voice_ai.main:app --reload
```

## Documentation

- **[CLAUDE.md](CLAUDE.md)** - Developer guide & architecture
- **[VOICE-AI.md](VOICE-AI.md)** - Project vision & provider comparison
- **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** - System design
- **[docs/CODE_GUIDE.md](docs/CODE_GUIDE.md)** - Key files explained

## Project Structure

```
src/voice_ai/
├── api/routes/       # HTTP/WebSocket endpoints
├── services/         # Business logic & orchestration
├── providers/        # External API wrappers
└── tests/            # Test suite
```

## License

MIT
