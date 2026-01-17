# Voice AI POC - Technical Implementation Plan

## Overview

Build a **modular, pluggable** Voice AI system where every component can be swapped. Test multiple providers, compare performance, and demonstrate production deployment.

See `VOICE-AI.md` for the high-level vision.

---

## Architecture: Pluggable Provider System

```
┌──────────────────────────────────────────────────────────────────────────┐
│                           FastAPI Application                             │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │                      Provider Interfaces                            │ │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐│ │
│  │  │ PhoneGW  │ │   STT    │ │   LLM    │ │   TTS    │ │ VectorDB ││ │
│  │  │Interface │ │Interface │ │Interface │ │Interface │ │Interface ││ │
│  │  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘│ │
│  └───────┼────────────┼────────────┼────────────┼────────────┼──────┘ │
│          │            │            │            │            │         │
│  ┌───────┼────────────┼────────────┼────────────┼────────────┼──────┐ │
│  │       ▼            ▼            ▼            ▼            ▼      │ │
│  │ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐│ │
│  │ │   VAPI   │ │ Deepgram │ │   Groq   │ │ Cartesia │ │ PgVector ││ │
│  │ │  Twilio  │ │ Assembly │ │  OpenAI  │ │ Deepgram │ │ Pinecone ││ │
│  │ │  Telnyx  │ │  Whisper │ │  Gemini  │ │ElevenLabs│ │  Qdrant  ││ │
│  │ │SignalWire│ │  Google  │ │  Claude  │ │  PlayHT  │ │  Chroma  ││ │
│  │ └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘│ │
│  │                     Concrete Implementations                     │ │
│  └──────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## Project Structure

```
voice_ai/
├── src/
│   └── voice_ai/
│       ├── __init__.py
│       ├── main.py                    # FastAPI entry point
│       ├── config.py                  # Settings (pydantic-settings)
│       │
│       ├── providers/                 # Pluggable provider system
│       │   ├── __init__.py
│       │   ├── base.py                # Abstract interfaces
│       │   │
│       │   ├── phone/                 # Phone/PSTN gateway
│       │   │   ├── __init__.py
│       │   │   ├── base.py            # PhoneGatewayInterface
│       │   │   ├── vapi.py
│       │   │   ├── twilio.py
│       │   │   └── telnyx.py
│       │   │
│       │   ├── stt/                   # Speech-to-Text
│       │   │   ├── __init__.py
│       │   │   ├── base.py            # STTInterface
│       │   │   ├── deepgram.py
│       │   │   ├── assemblyai.py
│       │   │   └── whisper.py
│       │   │
│       │   ├── llm/                   # Language Models
│       │   │   ├── __init__.py
│       │   │   ├── base.py            # LLMInterface
│       │   │   ├── groq.py
│       │   │   ├── openai.py
│       │   │   ├── gemini.py
│       │   │   └── claude.py
│       │   │
│       │   ├── tts/                   # Text-to-Speech
│       │   │   ├── __init__.py
│       │   │   ├── base.py            # TTSInterface
│       │   │   ├── cartesia.py
│       │   │   ├── deepgram.py
│       │   │   └── elevenlabs.py
│       │   │
│       │   └── vectordb/              # Vector Databases
│       │       ├── __init__.py
│       │       ├── base.py            # VectorDBInterface
│       │       ├── pgvector.py
│       │       ├── pinecone.py
│       │       └── qdrant.py
│       │
│       ├── services/                  # Business logic
│       │   ├── __init__.py
│       │   ├── rag.py                 # RAG retrieval
│       │   ├── survey.py              # Phone survey logic
│       │   ├── booking.py             # Booking logic
│       │   └── orchestrator.py        # Pipeline orchestration
│       │
│       ├── api/                       # API routes
│       │   ├── __init__.py
│       │   ├── routes/
│       │   │   ├── __init__.py
│       │   │   ├── health.py
│       │   │   ├── webhook.py         # Incoming call webhooks
│       │   │   ├── admin.py           # Config & management
│       │   │   └── benchmark.py       # Provider comparison endpoints
│       │   └── dependencies.py
│       │
│       ├── models/                    # Data models
│       │   ├── __init__.py
│       │   ├── schemas.py             # Pydantic schemas
│       │   └── database.py            # SQLAlchemy/SQLModel
│       │
│       └── db/                        # Database connections
│           ├── __init__.py
│           └── postgres.py
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── providers/                     # Test each provider
│   ├── services/
│   └── api/
│
├── scripts/
│   ├── ingest_bitext.py              # Load Bitext dataset
│   ├── benchmark_stt.py              # Compare STT providers
│   ├── benchmark_tts.py              # Compare TTS providers
│   └── benchmark_llm.py              # Compare LLM providers
│
├── data/
│   └── bitext/                        # Downloaded dataset
│
├── infra/
│   ├── docker/
│   │   ├── Dockerfile
│   │   └── docker-compose.yml
│   ├── aws/
│   │   ├── ec2-setup.sh
│   │   ├── fargate/
│   │   └── lambda/
│   └── caddy/
│       └── Caddyfile
│
├── docs/
│   └── provider-comparison.md         # Benchmark results
│
├── .env.example
├── .gitignore
├── pyproject.toml
├── VOICE-AI.md                        # High-level vision
├── PLAN.md                            # This file
├── SCRIPT.md                          # Video script
└── README.md
```

---

## Implementation Phases

### Phase 1: Project Foundation
- [ ] Project structure setup
- [ ] pyproject.toml with dependencies
- [ ] Config management (pydantic-settings)
- [ ] FastAPI skeleton with health endpoints
- [ ] Docker compose for local dev (Postgres)
- [ ] Provider interface definitions (abstract base classes)

### Phase 2: Provider Implementations (STT)
- [ ] STT interface definition
- [ ] Deepgram implementation
- [ ] AssemblyAI implementation
- [ ] Whisper (local) implementation
- [ ] Benchmark script for STT comparison

### Phase 3: Provider Implementations (LLM)
- [ ] LLM interface definition
- [ ] Groq (Llama) implementation
- [ ] OpenAI implementation
- [ ] Gemini implementation
- [ ] Function calling support for all

### Phase 4: Provider Implementations (TTS)
- [ ] TTS interface definition
- [ ] Cartesia implementation
- [ ] Deepgram TTS implementation
- [ ] ElevenLabs implementation
- [ ] Benchmark script for TTS comparison

### Phase 5: RAG System
- [ ] VectorDB interface definition
- [ ] PgVector implementation
- [ ] Pinecone implementation (optional)
- [ ] Bitext dataset ingestion
- [ ] RAG retrieval service
- [ ] Test Q&A flow

### Phase 6: Phone Integration
- [ ] Phone gateway interface
- [ ] VAPI implementation (webhook handling)
- [ ] Full pipeline: Phone → STT → LLM → TTS → Phone
- [ ] Test with real call

### Phase 7: Use Case - Phone Survey
- [ ] Survey service (questions, DB writes)
- [ ] Survey data models
- [ ] Survey function definitions
- [ ] Test full survey flow

### Phase 8: Use Case - Booking Agent
- [ ] Booking service
- [ ] Booking data models
- [ ] Availability checking
- [ ] Booking creation
- [ ] Test full booking flow

### Phase 9: AWS Deployment (EC2)
- [ ] EC2 instance setup
- [ ] Caddy HTTPS configuration
- [ ] PostgreSQL (RDS or local)
- [ ] Application deployment
- [ ] Domain configuration
- [ ] Test with real phone number

### Phase 10: Scaling Demo (Fargate)
- [ ] Dockerize application
- [ ] Push to ECR
- [ ] ECS task definition
- [ ] Fargate service setup
- [ ] ALB configuration
- [ ] Auto-scaling demonstration

### Phase 11: Provider Benchmarks & Comparison
- [ ] Run all benchmark scripts
- [ ] Document latency results
- [ ] Document quality results
- [ ] Document cost comparison
- [ ] Update provider-comparison.md

### Phase 12: Native Voice Models
- [ ] OpenAI Realtime API integration
- [ ] Gemini Live integration (if available)
- [ ] Side-by-side comparison
- [ ] Document trade-offs

---

## Provider Interfaces (Key Abstractions)

### STT Interface
```python
class STTProvider(ABC):
    @abstractmethod
    async def transcribe_stream(self, audio_stream: AsyncIterator[bytes]) -> AsyncIterator[str]:
        """Real-time streaming transcription"""
        pass

    @abstractmethod
    async def transcribe_file(self, audio_file: bytes) -> str:
        """Batch transcription"""
        pass
```

### LLM Interface
```python
class LLMProvider(ABC):
    @abstractmethod
    async def complete(self, messages: list[Message], tools: list[Tool] | None = None) -> LLMResponse:
        """Generate completion with optional function calling"""
        pass

    @abstractmethod
    async def stream_complete(self, messages: list[Message]) -> AsyncIterator[str]:
        """Streaming completion"""
        pass
```

### TTS Interface
```python
class TTSProvider(ABC):
    @abstractmethod
    async def synthesize(self, text: str, voice: str | None = None) -> bytes:
        """Convert text to audio"""
        pass

    @abstractmethod
    async def synthesize_stream(self, text: str) -> AsyncIterator[bytes]:
        """Streaming synthesis for lower latency"""
        pass
```

### VectorDB Interface
```python
class VectorDBProvider(ABC):
    @abstractmethod
    async def upsert(self, documents: list[Document]) -> None:
        """Insert or update documents"""
        pass

    @abstractmethod
    async def search(self, query: str, top_k: int = 5) -> list[SearchResult]:
        """Semantic search"""
        pass
```

---

## Configuration Example

```python
# config.py
class Settings(BaseSettings):
    # Provider selection
    stt_provider: Literal["deepgram", "assemblyai", "whisper"] = "deepgram"
    llm_provider: Literal["groq", "openai", "gemini", "claude"] = "groq"
    tts_provider: Literal["cartesia", "deepgram", "elevenlabs"] = "cartesia"
    vectordb_provider: Literal["pgvector", "pinecone", "qdrant"] = "pgvector"
    phone_provider: Literal["vapi", "twilio", "telnyx"] = "vapi"

    # Provider API keys
    deepgram_api_key: str | None = None
    assemblyai_api_key: str | None = None
    groq_api_key: str | None = None
    openai_api_key: str | None = None
    # ... etc

    # Database
    database_url: str = "postgresql://localhost/voice_ai"

    model_config = SettingsConfigDict(env_file=".env")
```

---

## Benchmark Metrics

For each provider comparison, measure:

| Metric | Description |
|--------|-------------|
| **Latency (P50, P95, P99)** | Time to first byte, total time |
| **Accuracy** | WER for STT, MOS for TTS |
| **Cost** | Per minute/request |
| **Reliability** | Error rate, uptime |
| **Features** | Streaming, languages, customization |

---

## Free Tier Strategy

| Provider | Free Tier | Strategy |
|----------|-----------|----------|
| VAPI | $10 + free number | Use for phone only |
| Deepgram | $200 credits | Primary STT/TTS |
| AssemblyAI | $50 credits | Comparison testing |
| Groq | Free tier | Primary LLM (fast) |
| OpenAI | Pay as you go | Function calling tests |
| Gemini | Free tier | Comparison testing |
| Cartesia | Free tier | Primary TTS |
| Pinecone | Free tier | If PgVector not enough |
| AWS | Free tier (12 months) | EC2 t2.micro, RDS |

**Estimated total cost for full POC: $10-30** (mostly domain + some API overages)

---

## Testing Strategy

1. **Unit tests** - Each provider implementation
2. **Integration tests** - Full pipeline with mocked providers
3. **E2E tests** - Real calls to real providers (manual)
4. **Benchmark tests** - Automated comparison scripts

---

## Dependencies (pyproject.toml preview)

```toml
[project]
dependencies = [
    "fastapi>=0.109.0",
    "uvicorn[standard]>=0.27.0",
    "pydantic>=2.5.0",
    "pydantic-settings>=2.1.0",
    "httpx>=0.26.0",
    "sqlalchemy>=2.0.0",
    "asyncpg>=0.29.0",
    "pgvector>=0.2.0",
    "deepgram-sdk>=3.0.0",
    "openai>=1.0.0",
    "anthropic>=0.18.0",
    "google-generativeai>=0.3.0",
    "groq>=0.4.0",
    "datasets>=2.16.0",        # For Bitext loading
    "python-dotenv>=1.0.0",
]
```

---

## Next Immediate Steps

1. Create pyproject.toml and install dependencies
2. Set up config.py with provider selection
3. Define abstract interfaces for all providers
4. Implement first STT provider (Deepgram)
5. Implement first LLM provider (Groq)
6. Implement first TTS provider (Cartesia)
7. Wire up basic pipeline (no phone yet)
8. Add phone integration (VAPI webhook)
9. Test first end-to-end call
