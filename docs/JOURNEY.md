# Voice AI Journey: Lessons Learned

## The Async Battle (CRITICAL LESSON)

### What We Tried First
- Adapter pattern with abstract base classes
- Sync DeepgramClient with threading hacks
- Manual message history management for LLM

### The Turning Point
**User's mandate: "I am staunchly in the async camp. No threading."**

This forced us to prove AsyncDeepgramClient works, which led to breakthrough.

### What Actually Works (PROVEN)
✅ **100% async/await** - No threading, no `ThreadPoolExecutor`, no sync hacks
✅ **AsyncDeepgramClient** - Native async Deepgram SDK (proven in `tests/test_async_deepgram.py`)
✅ **Async event handlers** - `async def on_stt_message(message)` works perfectly
✅ **OpenAI Responses API** - Built-in conversation state management

### Key Insight
**The reference implementation we found used sync handlers (`def`), but OUR tests proved async handlers (`async def`) work fine.** Don't blindly copy - test your assumptions!

---

## Audio Format Conversion Pitfalls

### Problem 1: Deprecated `audioop` Module
**Error:** `DeprecationWarning: 'audioop' is deprecated and slated for removal in Python 3.13`

**First attempt:** Try to suppress warning
**What worked:** Complete rewrite using NumPy + scipy

### Implementation: G.711 μ-law Codec
We implemented the full μ-law codec using bit manipulation:
- Extract sign, exponent, mantissa from 8-bit samples
- Decode using formula: `linear = ((mantissa << 3) + 0x84) << exponent`
- Apply sign and scale to int16 range

**Lesson:** When a library is deprecated, don't fight it - use modern alternatives.

---

## STT Streaming: The Critical Bug

### The Bug
**Symptoms:** Call connected, audio sent, but NO transcription output.

**Logs showed:**
```
Received audio chunk: 640 bytes (state: listening)
Received audio chunk: 640 bytes (state: listening)
Stream stopped
```

### Root Cause
Original implementation:
1. Buffered audio chunks
2. Sent all chunks to STT at once
3. **Closed STT connection immediately**
4. New audio chunks had nowhere to go!

### The Fix: Persistent Connection
```python
# ❌ WRONG - Closes connection after first batch
async def handle_audio():
    connection = await client.listen.v2.connect(...)
    await connection.send_media(audio)
    await connection.close()  # Connection closed!

# ✅ RIGHT - Keep connection open for entire call
async def start():
    self.stt_connection = await client.listen.v2.connect().__aenter__()
    self.stt_listen_task = asyncio.create_task(
        self.stt_connection.start_listening()
    )
    # Connection stays open - continuously streams audio!

async def handle_audio_chunk(chunk):
    await self.stt_connection.send_media(chunk)  # Send directly!
```

**Lesson:** For **live calls**, STT connection must stay open. For **file transcription**, batch processing works. Different use cases need different architectures.

---

## End-of-Turn Detection Optimization

### The Problem
**Default Deepgram Flux settings:**
- `eot_threshold=0.7` (default)
- `eot_timeout_ms=5000` (5 seconds!)

**Result:** Waiting up to 5 seconds after user stops talking = terrible UX.

### The Fix
```python
self.stt_connection = await client.listen.v2.connect(
    model="flux-general-en",
    eot_threshold="0.6",      # Lower = faster detection
    eot_timeout_ms="3000",    # 3 seconds instead of 5
)
```

**Result:** Turn detection cut from ~5s to ~3s.

**Future optimization:** Add `eager_eot_threshold` to start LLM processing BEFORE user finishes speaking.

---

## Logging: The Bombardment

### The Problem
**User:** "The logs are bombarding me!"

**Cause:** DEBUG logging for events that happen 50+ times per second:
```python
# ❌ This logs 50+ times/second!
logger.debug(f"Audio chunk: {len(chunk)} bytes")
```

### The Fix
1. **Use INFO level globally** - DEBUG is too noisy for real-time audio
2. **Log first occurrence only**:
```python
if not hasattr(self, "_audio_sent"):
    self._audio_sent = True
    logger.info(f"🔊 Sending audio: {len(pcm_data)} bytes")
```
3. **Use emojis for visual clarity**: 📞 🎤 ✓ → ←
4. **Silence external libraries**:
```python
logging.getLogger("httpx").setLevel(logging.WARNING)
```

**Lesson:** High-frequency events need smart logging strategies.

---

## TTS Audio Playback Mystery

### Current Status (v0)
✅ **Pipeline works end-to-end:**
- STT transcribes: "What is the capital of Brazil?"
- LLM generates response
- TTS synthesizes audio (9 chunks received)
- Audio sent to Twilio (20+ chunks)

❌ **But caller doesn't hear audio**

### Observations
1. **Audio is being sent** - Logs confirm 20+ chunks sent to Twilio
2. **Format conversion working** - PCM 1280 bytes → μ-law 320 bytes
3. **streamSid present** - Twilio message format correct

### Next Debug Steps
- Verify μ-law encoding is correct (test with known good audio)
- Check Twilio media message timing (might need rate limiting)
- Test with simple beep/tone to isolate TTS from conversion issue
- Check if Twilio requires specific chunk sizes

---

## What We Built (v0 Foundation)

### Core Components
1. **VoiceSession** (`voice_session.py`)
   - Format-agnostic orchestrator (PCM 16kHz internally)
   - Persistent STT connection for continuous streaming
   - Sentence-by-sentence TTS synthesis
   - Full async architecture

2. **TwilioVoiceSession** (`voice_ws.py`)
   - Extends VoiceSession for Twilio format
   - Handles μ-law ↔ PCM conversion
   - Manages streamSid for media messages

3. **Audio Utils** (`audio_utils.py`)
   - G.711 μ-law codec (NumPy implementation)
   - Sample rate conversion (8kHz ↔ 16kHz)
   - High-quality polyphase filtering

4. **Providers** (all 100% async)
   - DeepgramSTT (AsyncDeepgramClient)
   - OpenAI LLM (Responses API)
   - DeepgramTTS (AsyncDeepgramClient)

### Test Coverage
- `test_async_deepgram.py` - Proves AsyncDeepgramClient works
- `test_async_providers.py` - Validates async providers
- `test_voice_pipeline.py` - End-to-end STT → LLM → TTS

---

## Philosophy: 100% Async

**User's mandate shaped the entire architecture:**

> "I am staunchly in the async camp. If this doesn't use async functions, fuck this implementation."

**Result:**
- Zero threading code
- All providers use native async clients
- Event handlers are `async def`
- Better resource utilization
- Simpler reasoning (no locks, no synchronization)
- Future-proof for scale

**This decision forced us to dig deeper and find the RIGHT solution instead of quick hacks.**

---

## Next Steps (v1 Roadmap)

### Immediate (fix audio playback)
1. Debug why Twilio doesn't play audio
2. Test μ-law encoding correctness
3. Verify audio chunk timing/buffering

### Short-term (latency optimization)
1. Implement `eager_eot_threshold` for speculative LLM starts
2. Handle `TurnResumed` events (cancel speculative responses)
3. Optimize LLM prompt for faster responses

### Medium-term (features)
1. Browser WebSocket support (WebM/Opus audio)
2. Multi-provider support (AssemblyAI, ElevenLabs, etc.)
3. RAG integration for knowledge-based responses

### Long-term (scale)
1. Connection pooling
2. Rate limiting
3. Metrics/monitoring
4. Multi-tenant support

---

## Key Takeaways

1. **Trust your instincts** - User insisted on async-only, which led to better architecture
2. **Test your assumptions** - Reference code used sync handlers, but async works fine
3. **Different use cases = different patterns** - File transcription ≠ live call streaming
4. **Smart logging is critical** - High-frequency events need special handling
5. **Read the docs** - Deepgram's EOT parameters can cut latency significantly
6. **Ship v0 early** - Foundation is solid even if audio playback needs debugging
