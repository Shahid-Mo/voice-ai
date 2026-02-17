# Production Voice AI — Architecture From First Principles

A fully functional voice agent built from scratch using a cascaded architecture: Twilio (telephony) → Deepgram Flux (STT) → OpenAI (LLM) → Deepgram Aura (TTS). No managed platforms. No orchestration wrappers. Every WebSocket, every codec conversion, every millisecond accounted for.

This is the architecture behind a production system deployed to 50+ franchise locations with sub-900ms round-trip latency and legacy ERP integration.

The project uses a hotel concierge (The Hotel Continental) as the reference implementation.

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│  TELEPHONY (Twilio)                                 │
│  PSTN → SIP → mulaw 8kHz ↔ WebSocket bidir stream  │
└──────────────────────┬──────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────┐
│  🎙️ STT — Persistent Connection (Outer Ring)        │
│  Deepgram Flux · PCM 16kHz · Always listening        │
│                                                      │
│  ┌──────────────────┐  ┌──────────────────┐         │
│  │  💭 LLM          │  │  🔊 TTS          │         │
│  │  OpenAI          │  │  Deepgram Aura   │         │
│  │  Per-turn        │  │  Per-turn        │         │
│  │  Streaming       │  │  Streaming       │         │
│  └──────────────────┘  └──────────────────┘         │
│           Ephemeral Turn Workers                     │
└─────────────────────────────────────────────────────┘
```

**Two connection lifecycles:**
- **STT (Outer Ring):** Opens when the call starts, closes when the call ends. Continuous audio context for end-of-turn detection.
- **LLM + TTS (Turn Workers):** Spin up per turn, tear down after. Stateless from their perspective.

---

## Latency Breakdown

```
Bob speaks → Flux EOT detection (~300ms) → LLM TTFB (~200ms) → TTS TTFB (~150ms) → Bob hears AI
             ◄────────────────────── ~650ms total ──────────────────────►
```

Every optimization compounds across hops. Faster EOT saves 200ms. Faster LLM saves 100ms. Faster TTS saves 50ms.

---

## Key Design Decisions

### End-of-Turn Detection
Silence-based VAD fails when callers pause mid-sentence. Deepgram Flux combines acoustic and linguistic signals — recognizing that "I have a reservation under the name..." is semantically incomplete — and holds the buffer until the thought is finished.

Tunable parameters:
- `eot_threshold`: Confidence threshold for end-of-turn (default 0.7, running 0.6 for faster detection)
- `eot_timeout_ms`: Hard ceiling after speech (default 5000ms, running 3000ms)

### Sentence Buffering
LLM tokens stream into a buffer. Regex scans for sentence boundaries (`. `, `? `, `! `, `\n\n`). Complete sentences dispatch to TTS immediately. The caller hears natural speech while the LLM is still generating.

### Barge-In / Interruption Handling
Epoch-based invalidation for in-flight audio. When the user interrupts:

1. Epoch increments — all stale TTS chunks self-discard on comparison
2. Twilio playback buffer cleared
3. LLM stream cancelled
4. TTS connection cancelled

Three-layer filter prevents false triggers:
- **Latch:** One interrupt per utterance (prevents "actually I want to change" from firing 5 handlers)
- **Debounce:** 400ms window between interrupts (catches echo and noise bursts)
- **Min character threshold:** Interim transcripts < 4 chars ignored ("mm", "ok", "uh" = back-channel, not interruption)

### Codec Pipeline
```
IN:  Twilio → JSON → Base64 decode → mulaw 8kHz → PCM 16kHz → Deepgram Flux
OUT: Deepgram Aura → PCM 16kHz → mulaw 8kHz → Base64 encode → JSON → Twilio
```

### Control Plane / Data Plane Separation
- **HTTP POST webhook:** Routing decisions (AI vs. human, canary percentages, error handling)
- **WebSocket:** Audio processing (STT, LLM, TTS orchestration)

These are two different concerns and they stay apart. Enables shadow mode, canary rollouts, and A/B testing without touching the audio pipeline.

---

## Stack

| Layer | Provider | Role |
|-------|----------|------|
| Telephony | Twilio | PSTN bridge, WebSocket streaming, mulaw codec |
| STT | Deepgram Flux | Persistent connection, contextual end-of-turn detection |
| LLM | OpenAI | Streaming completion, function calling, conversation context |
| TTS | Deepgram Aura | Per-turn streaming synthesis, flush-on-send |

The architecture is modular by design. Swap any component without changing the orchestration logic.

---

## Series

Each video documents a layer of this system. Code evolves with the series.

| # | Topic | Video |
|---|-------|-------|
| 1 | Cascade vs. Native architectures | [Watch](https://youtu.be/PRa4ClK405s) |
| 2 | Twilio WebSocket streaming — PSTN to PCM | Coming soon |
| 3 | Happy path pipeline — STT→LLM→TTS orchestration | Coming soon |
| 4 | Barge-in & interruption handling | Coming soon |
| 5 | LLM for voice — TTFB, context chaining, throughput | Coming soon |
| 6 | Function calling & MCP | Coming soon |
| 7 | RAG — Hub-and-spoke model with Supabase | Coming soon |
| 8 | Pipecat & VAPI comparison | Coming soon |
| 9 | Deployment | Coming soon |
| 10 | Native voice models | Coming soon |

---

## Getting Started

### Prerequisites
- Python 3.11+
- Twilio account with a phone number
- Deepgram API key
- OpenAI API key
- ngrok (for local development)

### Setup

```bash
git clone https://github.com/Shahid-Mo/voice-ai-from-scratch.git
cd voice-ai-from-scratch

python -m venv venv
source venv/bin/activate

pip install -r requirements.txt

cp .env.example .env
# Add your API keys to .env
```

### Run

```bash
# Start ngrok tunnel
ngrok http 8000

# Update Twilio webhook URL to your ngrok tunnel
# Start the server
python main.py
```

Call your Twilio number. The concierge picks up.

---

## Production Rollout Strategy

The control plane / data plane split enables phased deployment:

1. **Shadow mode:** AI listens alongside human agents, generates responses silently, logs everything. Zero customer risk.
2. **Canary:** 5% → 10% → 25% of calls routed to AI. Redis-based lookup in the POST handler.
3. **Full deployment:** AI handles all calls. Human escalation path always available.

---

## License

MIT

---

Built by [Shahid Mohiuddin](https://shahid-mo.github.io) · [LinkedIn](https://linkedin.com/in/shahid-mo) · [YouTube](https://youtube.com/@TheSolutionEngineer)
