# Voice AI Architecture (v0)

## System Overview

```
┌─────────────┐
│   Phone     │ (Twilio PSTN)
└──────┬──────┘
       │ μ-law 8kHz
       ↓
┌──────────────────────────────────────────┐
│         Twilio Media Streams             │
│         (WebSocket JSON)                 │
└──────┬───────────────────────────────────┘
       │ Base64 μ-law 8kHz
       ↓
┌──────────────────────────────────────────┐
│      TwilioVoiceSession                  │
│      (Audio Format Adapter)              │
│      • Decode Base64                     │
│      • μ-law → PCM 16kHz                 │
│      • PCM 16kHz → μ-law                 │
└──────┬───────────────────────────────────┘
       │ PCM 16kHz (internal format)
       ↓
┌──────────────────────────────────────────┐
│         VoiceSession                     │
│         (Format-Agnostic Orchestrator)   │
│                                          │
│   ┌─────────────────────────────────┐   │
│   │  Persistent STT Connection      │   │
│   │  (Continuous Streaming)         │   │
│   └────────┬────────────────────────┘   │
│            ↓ Transcript                 │
│   ┌─────────────────────────────────┐   │
│   │  LLM Streaming                  │   │
│   │  (Sentence-by-Sentence)         │   │
│   └────────┬────────────────────────┘   │
│            ↓ Text                        │
│   ┌─────────────────────────────────┐   │
│   │  TTS Streaming                  │   │
│   │  (Audio Synthesis)              │   │
│   └────────┬────────────────────────┘   │
│            ↓ PCM Audio                   │
└────────────┼──────────────────────────────┘
             │
             ↓
       (Back to caller)
```

---

## Core Components

### 1. VoiceSession (Format-Agnostic Core)

**Location:** `src/voice_ai/services/voice_session.py`

**Responsibility:** Orchestrate STT → LLM → TTS pipeline in real-time

**Key Design:**
- **Internal format:** PCM linear16 16kHz mono (what Deepgram expects)
- **Endpoints handle conversion:** μ-law for Twilio, future: WebM for browsers
- **100% async:** No threading, all `async`/`await`

**Lifecycle:**

```python
# 1. Initialize
session = VoiceSession(websocket)

# 2. Start persistent STT connection
await session.start()
# → Opens WebSocket to Deepgram Flux
# → Registers async event handlers
# → Starts background listening task
# → Connection stays open for ENTIRE call

# 3. Stream audio continuously
while call_active:
    chunk = await receive_audio()
    await session.handle_audio_chunk(chunk)
    # → Sends directly to persistent STT connection
    # → No buffering!

# 4. On turn detection (user stops talking)
# → EndOfTurn event triggers on_turn_end()
# → Runs LLM + TTS pipeline
# → Returns to listening (STT connection still open!)

# 5. Cleanup
await session.cleanup()
# → Closes STT connection
# → Exits context manager
```

**State Machine:**
```
idle → listening → processing → speaking → listening → ...
```

---

### 2. TwilioVoiceSession (Twilio Adapter)

**Location:** `src/voice_ai/api/routes/voice_ws.py`

**Responsibility:** Adapt Twilio's format to VoiceSession's PCM format

**Twilio Media Streams Protocol:**
```json
// Incoming (audio from phone)
{
  "event": "media",
  "media": {
    "payload": "base64_encoded_mulaw_8khz"
  }
}

// Outgoing (audio to phone)
{
  "event": "media",
  "streamSid": "MZ...",
  "media": {
    "payload": "base64_encoded_mulaw_8khz"
  }
}
```

**Audio Flow (Incoming):**
```
Twilio JSON
  → Base64 decode
  → μ-law 8kHz bytes
  → μ-law decode (G.711)
  → PCM 16-bit samples
  → Resample 8kHz → 16kHz
  → VoiceSession.handle_audio_chunk()
```

**Audio Flow (Outgoing):**
```
VoiceSession.send_audio(pcm_16khz)
  → Resample 16kHz → 8kHz
  → μ-law encode (G.711)
  → Base64 encode
  → Wrap in Twilio JSON
  → WebSocket.send_text()
```

---

### 3. Audio Utils (Format Conversion)

**Location:** `src/voice_ai/audio_utils.py`

**Replaces:** Deprecated `audioop` module

**Implementation:** NumPy + scipy (modern, maintained)

#### G.711 μ-law Codec

**Encoding (PCM → μ-law):**
```python
# Extract sign bit
sign = (pcm < 0).astype(np.int32)

# Work with absolute value
pcm = np.abs(pcm) + 33  # Add bias

# Find exponent (3 bits) - position of highest set bit
exponent = ...  # Logarithmic compression

# Extract mantissa (4 bits)
mantissa = (pcm >> (exponent + 3)) & 0x0F

# Combine: sign (1) + exponent (3) + mantissa (4) = 8 bits
mulaw = (sign << 7) | (exponent << 4) | mantissa

# Invert bits (μ-law standard)
mulaw = ~mulaw & 0xFF
```

**Why μ-law?**
- Telephony standard (US/Japan)
- Logarithmic compression (better for voice)
- 8-bit samples (half the bandwidth of 16-bit PCM)

#### Sample Rate Conversion

**8kHz ↔ 16kHz:**
```python
from scipy import signal

# Calculate ratio using GCD
# 8kHz → 16kHz: up=2, down=1
# 16kHz → 8kHz: up=1, down=2

resampled = signal.resample_poly(samples, up, down)
# Polyphase filtering = high quality, efficient
```

---

## Async Architecture

### Event Handler Pattern

**DeepgramSTT (Persistent Connection):**
```python
async def start():
    # Open connection
    connection = await client.listen.v2.connect(
        model="flux-general-en",
        encoding="linear16",
        sample_rate=16000,
        eot_threshold="0.6",      # Optimized
        eot_timeout_ms="3000",
    ).__aenter__()

    # Register ASYNC event handler
    async def on_stt_message(message):
        if message.type == "TurnInfo":
            if message.event == "EndOfTurn":
                await self.on_turn_end(message.transcript)

    connection.on(EventType.MESSAGE, on_stt_message)

    # Start background listening task
    listen_task = asyncio.create_task(
        connection.start_listening()
    )
```

**Key insight:** Event handlers are `async def`, not `def`. Reference implementations use sync, but async works and integrates better.

### DeepgramTTS (Streaming Synthesis)

```python
async with tts_client.speak.v1.connect(...) as connection:
    # Register audio handler
    async def on_tts_audio(message):
        if isinstance(message, bytes):
            await self.send_audio(message)  # Async!

    connection.on(EventType.MESSAGE, on_tts_audio)

    # Start listening in background
    listen_task = asyncio.create_task(connection.start_listening())

    # Send text for synthesis
    await connection.send_text(SpeakV1Text(text="Hello world"))
    await connection.send_flush(SpeakV1Flush(type="Flush"))

    # Audio chunks stream back asynchronously
```

---

## Sentence-by-Sentence Streaming

**Problem:** Waiting for full LLM response before TTS = high latency

**Solution:** Synthesize each sentence as soon as it's complete

```python
sentence_buffer = ""

async for llm_chunk in self.llm.stream_complete(...):
    sentence_buffer += llm_chunk

    # Check for sentence boundary
    if re.search(r"[.!?]\s*$", sentence_buffer):
        # Send sentence to TTS immediately
        await tts_connection.send_text(
            SpeakV1Text(text=sentence_buffer.strip())
        )
        await tts_connection.send_flush(SpeakV1Flush(type="Flush"))

        # Audio starts playing while LLM still generating!
        sentence_buffer = ""
```

**Result:** First audio plays while LLM still generating later sentences.

---

## Latency Breakdown (Current)

```
User stops speaking
  ↓
[0-3s] Turn detection (eot_timeout_ms=3000)
  ↓
[~7s] LLM first token (gpt-5-nano is slow)
  ↓
[~1s] LLM generates sentence
  ↓
[~1s] TTS synthesizes sentence
  ↓
[0.1s] Audio transmission
  ↓
Total: ~12s (NEEDS OPTIMIZATION)
```

**Low-hanging fruit:**
1. Add `eager_eot_threshold` → start LLM while user still talking (saves ~2s)
2. Optimize LLM prompt → faster generation
3. Consider faster model for simple queries

---

## Configuration

### End-of-Turn Detection (Flux)

```python
# Current (Simple Mode)
eot_threshold="0.6"      # Lower = faster detection
eot_timeout_ms="3000"    # 3 seconds max silence

# Future (Eager Mode - not yet implemented)
eager_eot_threshold="0.4"  # Start LLM early
eot_threshold="0.6"        # Confirm turn end
# Requires handling TurnResumed events!
```

**Trade-offs:**
- **Lower threshold** → faster, more false positives
- **Higher threshold** → more accurate, slower
- **Eager mode** → lower latency, more LLM calls, requires cancellation logic

---

## Provider Abstraction

### Current (Hardcoded)
```python
self.stt = AsyncDeepgramClient(...)
self.llm = OpenAILLM()
self.tts = DeepgramTTS()
```

### Future (Pluggable)
```python
# Settings control provider selection
stt_provider = get_provider(settings.stt_provider)
llm_provider = get_provider(settings.llm_provider)
tts_provider = get_provider(settings.tts_provider)
```

**Benefit:** Swap providers without code changes (compare quality, cost, latency)

---

## Testing Strategy

### Unit Tests (Provider Level)
```python
# tests/test_async_deepgram.py
async def test_async_stt():
    # Proves AsyncDeepgramClient works
    # No threading needed!
```

### Integration Tests (Pipeline Level)
```python
# tests/test_voice_pipeline.py
# Tests: STT → LLM → TTS end-to-end
```

### Manual Tests (Real Calls)
- Call Twilio number
- Verify transcription accuracy
- Check response quality
- Measure latency

---

## Known Issues (v0)

### 1. Audio Playback Not Working
- Pipeline executes (STT → LLM → TTS)
- Audio synthesized and sent to Twilio
- **But caller doesn't hear it**
- Next: Debug μ-law encoding, Twilio timing

### 2. High Latency (~12s)
- Turn detection: 0-3s (optimized)
- LLM generation: ~7s (gpt-5-nano is slow)
- TTS synthesis: ~1s
- Next: Add eager EOT, optimize prompts

### 3. Audio Chunk Mismatch
- TTS reports: 9 chunks received
- Twilio reports: 20+ chunks sent
- Likely resampling artifacts or late-arriving chunks
- Next: Investigate timing

---

## Deployment

### Current (Development)
```bash
uv run uvicorn voice_ai.main:app --reload --port 8000
```

### Production (TODO)
- Use gunicorn with uvicorn workers
- Add nginx reverse proxy
- Enable TLS (wss://)
- Environment-based config
- Health checks
- Metrics/logging aggregation

---

## Future Architecture (Multi-Channel)

```
                     ┌─────────────┐
                     │ VoiceSession│
                     │   (Core)    │
                     └──────┬──────┘
                            │ PCM 16kHz
            ┌───────────────┼───────────────┐
            │               │               │
    ┌───────▼─────┐  ┌──────▼──────┐  ┌────▼──────┐
    │   Twilio    │  │   Browser   │  │   Future  │
    │  (μ-law)    │  │   (WebM)    │  │  (Other)  │
    └─────────────┘  └─────────────┘  └───────────┘
```

**Same core logic, different audio adapters.**
