# Code Guide: Key Files Explained

## Directory Structure

```
src/voice_ai/
├── main.py                    # FastAPI app entry point
├── config.py                  # Settings (pydantic-settings)
├── audio_utils.py             # Audio format conversion (μ-law, resampling)
├── api/
│   └── routes/
│       ├── health.py          # Health check endpoints
│       └── voice_ws.py        # Twilio WebSocket endpoints ⭐
├── services/
│   └── voice_session.py       # Core orchestrator (STT→LLM→TTS) ⭐⭐⭐
└── providers/
    ├── stt/
    │   ├── base.py            # STT interface (future)
    │   └── deepgram.py        # Deepgram Flux STT
    ├── llm/
    │   ├── base.py            # LLM interface (future)
    │   └── openai.py          # OpenAI Responses API ⭐
    └── tts/
        ├── base.py            # TTS interface (future)
        └── deepgram.py        # Deepgram Aura TTS

tests/
├── test_async_deepgram.py     # Proves async pattern works ⭐
├── test_async_providers.py    # Provider validation
└── test_voice_pipeline.py     # End-to-end pipeline test

docs/
├── JOURNEY.md                 # Learning journey, pitfalls
├── ARCHITECTURE.md            # System design
└── CODE_GUIDE.md             # This file
```

---

## Core Files (Deep Dive)

### ⭐⭐⭐ `services/voice_session.py` (THE HEART)

**Purpose:** Format-agnostic voice AI orchestrator

**Key Classes:**

#### `VoiceSession`

**Initialization:**
```python
def __init__(self, websocket: WebSocket):
    self.stt_client = AsyncDeepgramClient(...)
    self.llm = OpenAILLM()
    self.tts = DeepgramTTS()

    # Persistent STT connection (stays open for entire call)
    self.stt_connection = None
    self.stt_listen_task = None
    self._stt_context_manager = None

    # Session state
    self.state: State = "idle" | "listening" | "processing" | "speaking"
    self.conversation_id: str | None = None
```

**Critical Methods:**

##### `async def start()`
Opens persistent STT connection for entire call:

```python
async def start(self):
    # Create context manager (like async with)
    self._stt_context_manager = self.stt_client.listen.v2.connect(
        model="flux-general-en",
        encoding="linear16",
        sample_rate=16000,
        eot_threshold="0.6",      # Optimized for speed
        eot_timeout_ms="3000",    # 3 seconds max
    )

    # Enter context manager
    self.stt_connection = await self._stt_context_manager.__aenter__()

    # Register ASYNC event handlers
    async def on_stt_message(message):
        if message.type == "TurnInfo" and message.event == "EndOfTurn":
            await self.on_turn_end(message.transcript)

    self.stt_connection.on(EventType.MESSAGE, on_stt_message)

    # Start background listening task
    self.stt_listen_task = asyncio.create_task(
        self.stt_connection.start_listening()
    )
```

**Why context manager?** Ensures proper cleanup even on errors.

##### `async def handle_audio_chunk(pcm_chunk)`
Sends audio directly to persistent STT connection:

```python
async def handle_audio_chunk(self, pcm_chunk: bytes):
    # No buffering! Send directly to open connection
    await self.stt_connection.send_media(pcm_chunk)
```

**Called 50+ times per second** - must be fast, no logging here.

##### `async def on_turn_end(transcript)`
Triggers LLM + TTS pipeline when user stops talking:

```python
async def on_turn_end(self, transcript: str):
    self.state = "processing"
    await self.process_llm_and_tts(transcript)
    self.state = "listening"  # Back to listening (STT still open!)
```

##### `async def process_llm_and_tts(user_input)`
The sentence-by-sentence streaming magic:

```python
async def process_llm_and_tts(self, user_input: str):
    # Create conversation on first turn
    if not self.conversation_id:
        self.conversation_id = await self.llm.create_conversation()

    # Open TTS connection (async with)
    async with self.tts.client.speak.v1.connect(...) as tts_connection:
        # Register audio handler
        async def on_tts_audio(message):
            if isinstance(message, bytes):
                await self.send_audio(message)  # To caller

        tts_connection.on(EventType.MESSAGE, on_tts_audio)
        listen_task = asyncio.create_task(tts_connection.start_listening())

        # Stream LLM and synthesize sentence-by-sentence
        sentence_buffer = ""

        async for llm_chunk in self.llm.stream_complete(user_input, ...):
            sentence_buffer += llm_chunk

            # Sentence complete? Synthesize NOW!
            if re.search(r"[.!?]\s*$", sentence_buffer):
                await tts_connection.send_text(...)
                await tts_connection.send_flush(...)
                sentence_buffer = ""  # Reset for next sentence
```

**Key insight:** First sentence starts playing while LLM still generating later sentences.

##### `async def cleanup()`
Properly closes STT connection:

```python
async def cleanup(self):
    if self.stt_connection:
        # Send close signal
        await self.stt_connection.send_close_stream(...)
        # Wait for listen task
        await self.stt_listen_task
        # Exit context manager
        await self._stt_context_manager.__aexit__(None, None, None)
```

---

### ⭐ `api/routes/voice_ws.py` (Twilio Integration)

**Purpose:** WebSocket endpoints for Twilio Media Streams

**Key Functions:**

#### `async def incoming_call(request)`
Twilio webhook - returns TwiML to connect call to WebSocket:

```python
@router.api_route("/incoming-call", methods=["GET", "POST"])
async def incoming_call(request: Request):
    host = request.headers.get("host")
    protocol = "wss" if "ngrok" in host else "ws"

    # TwiML XML tells Twilio to connect to our WebSocket
    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
    <Response>
        <Connect>
            <Stream url="{protocol}://{host}/ws/twilio" />
        </Connect>
    </Response>"""

    return Response(content=twiml, media_type="application/xml")
```

#### `async def twilio_websocket(websocket)`
Main WebSocket handler for bidirectional audio:

```python
@router.websocket("/ws/twilio")
async def twilio_websocket(websocket: WebSocket):
    await websocket.accept()
    session = TwilioVoiceSession(websocket)

    async for message in websocket.iter_text():
        data = json.loads(message)

        if data["event"] == "start":
            await session.on_start(data)
            await session.start()  # Open persistent STT

        elif data["event"] == "media":
            # Incoming audio from phone
            mulaw_audio = base64.b64decode(data["media"]["payload"])
            pcm_audio = mulaw_to_pcm_16k(mulaw_audio, input_rate=8000)
            await session.handle_audio_chunk(pcm_audio)

        elif data["event"] == "stop":
            await session.cleanup()
```

#### `class TwilioVoiceSession(VoiceSession)`
Extends VoiceSession to handle Twilio format:

```python
class TwilioVoiceSession(VoiceSession):
    async def on_start(self, start_data: dict):
        # Save streamSid for outgoing audio
        self.stream_sid = start_data["start"]["streamSid"]

    async def send_audio(self, pcm_data: bytes):
        # Override to convert PCM → Twilio format
        mulaw_audio = pcm_16k_to_mulaw(pcm_data, output_rate=8000)
        payload_b64 = base64.b64encode(mulaw_audio).decode()

        # Wrap in Twilio media message
        media_message = {
            "event": "media",
            "streamSid": self.stream_sid,
            "media": {"payload": payload_b64},
        }

        await self.websocket.send_text(json.dumps(media_message))

    async def send_json(self, data: dict):
        # Override to prevent raw JSON to Twilio
        # Only audio sent via send_audio()
        pass
```

---

### ⭐ `providers/llm/openai.py` (OpenAI Integration)

**Purpose:** OpenAI LLM using Responses API (conversation state management)

**Key Methods:**

#### `async def create_conversation()`
Creates persistent conversation for state management:

```python
async def create_conversation(self) -> str:
    conversation = await self._client.conversations.create()
    return conversation.id  # Use this for all turns
```

**Benefit:** No manual message history tracking!

#### `async def stream_complete(input, conversation_id)`
Stream LLM response token-by-token:

```python
async def stream_complete(self, input: str, conversation_id: str):
    params = {
        "model": self.model,  # gpt-5-nano
        "temperature": self.temperature,
        "input": input,
        "conversation": conversation_id,  # Auto-manages context
    }

    async with self._client.responses.stream(**params) as stream:
        async for event in stream:
            if event.type == "response.output_text.delta":
                yield event.delta  # Text chunk
```

**Returns:** Async iterator yielding text chunks as they're generated

---

### `audio_utils.py` (Format Conversion)

**Purpose:** Convert between audio formats (replaces deprecated `audioop`)

**Key Functions:**

#### `mulaw_to_pcm_16k(mulaw_data, input_rate)`
Twilio → Deepgram conversion:

```python
def mulaw_to_pcm_16k(mulaw_data: bytes, input_rate: int = 8000) -> bytes:
    # 1. Decode μ-law to PCM int16
    pcm_samples = _mulaw_decode(mulaw_data)

    # 2. Resample 8kHz → 16kHz
    if input_rate != 16000:
        pcm_samples = _resample(pcm_samples, input_rate, 16000)

    # 3. Return as bytes
    return pcm_samples.astype(np.int16).tobytes()
```

#### `pcm_16k_to_mulaw(pcm_data, output_rate)`
Deepgram → Twilio conversion:

```python
def pcm_16k_to_mulaw(pcm_data: bytes, output_rate: int = 8000) -> bytes:
    # 1. Convert bytes to int16 array
    pcm_samples = np.frombuffer(pcm_data, dtype=np.int16)

    # 2. Resample 16kHz → 8kHz
    if output_rate != 16000:
        pcm_samples = _resample(pcm_samples, 16000, output_rate)

    # 3. Encode to μ-law
    mulaw_bytes = _mulaw_encode(pcm_samples)

    return mulaw_bytes
```

#### `_mulaw_decode(mulaw_bytes)` / `_mulaw_encode(pcm_samples)`
G.711 μ-law codec implementation using NumPy bit manipulation:

```python
def _mulaw_decode(mulaw_bytes: bytes) -> np.ndarray:
    mulaw = np.frombuffer(mulaw_bytes, dtype=np.uint8).astype(np.int32)
    mulaw = ~mulaw & 0xFF  # Invert bits

    # Extract components
    sign = (mulaw & 0x80) >> 7
    exponent = (mulaw & 0x70) >> 4
    mantissa = mulaw & 0x0F

    # Decode formula
    linear = ((mantissa << 3) + 0x84) << exponent
    linear = linear - 0x84
    linear = np.where(sign == 0, linear, -linear)

    return linear.astype(np.int16)
```

#### `_resample(samples, src_rate, dst_rate)`
High-quality sample rate conversion:

```python
def _resample(samples: np.ndarray, src_rate: int, dst_rate: int):
    from math import gcd
    from scipy import signal

    # Calculate ratio (e.g., 8kHz→16kHz: up=2, down=1)
    divisor = gcd(src_rate, dst_rate)
    up = dst_rate // divisor
    down = src_rate // divisor

    # Polyphase filtering (high quality)
    resampled = signal.resample_poly(samples.astype(np.float32), up, down)
    return resampled.astype(samples.dtype)
```

---

## Testing Files

### ⭐ `tests/test_async_deepgram.py` (PROOF OF CONCEPT)

**Purpose:** Prove AsyncDeepgramClient works without threading

**Why critical?** This test convinced us to go 100% async.

```python
async def test_async_stt():
    client = AsyncDeepgramClient(...)

    async with client.listen.v2.connect(...) as connection:
        # ASYNC event handler (not sync!)
        async def message_handler(message):
            if message.type == "TurnInfo":
                print(f"Transcript: {message.transcript}")

        connection.on(EventType.MESSAGE, message_handler)
        listen_task = asyncio.create_task(connection.start_listening())

        # Send audio chunks
        for chunk in audio_chunks:
            await connection.send_media(chunk)  # Fully async!

        await connection.send_close_stream(...)
        await listen_task
```

**Lesson learned:** Reference implementations used `def` handlers, but `async def` works perfectly.

---

## Configuration Files

### `.env`
Environment variables (never commit!):

```bash
# Required
DEEPGRAM_API_KEY=your_key_here
OPENAI_API_KEY=your_key_here

# Optional
HOST=0.0.0.0
PORT=8000
DEBUG=true
```

### `config.py`
Pydantic settings with auto-loading:

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    deepgram_api_key: str
    openai_api_key: str
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False

    class Config:
        env_file = ".env"  # Auto-load from .env

settings = Settings()  # Access via settings.deepgram_api_key
```

---

## Common Patterns

### Pattern 1: Async Event Handlers
```python
# Register handler
async def on_event(message):
    await do_something_async(message)

connection.on(EventType.MESSAGE, on_event)
```

### Pattern 2: Background Tasks
```python
# Start long-running task in background
task = asyncio.create_task(long_running_operation())

# Later: wait for completion
await task
```

### Pattern 3: Context Managers
```python
# Manual context manager (for persistent connections)
cm = client.connect(...)
connection = await cm.__aenter__()
# ... use connection ...
await cm.__aexit__(None, None, None)

# Or use async with (auto cleanup)
async with client.connect(...) as connection:
    # ... use connection ...
    pass  # Auto cleanup on exit
```

### Pattern 4: Conditional Logging
```python
# High-frequency events - log first occurrence only
if not hasattr(self, "_logged_once"):
    self._logged_once = True
    logger.info("First chunk received")
```

---

## Debugging Tips

### 1. Enable Deepgram Logging
```python
import logging
logging.getLogger("deepgram").setLevel(logging.DEBUG)
```

### 2. Test Audio Conversion Separately
```python
# Create test audio
test_pcm = np.random.randint(-32768, 32767, 16000, dtype=np.int16).tobytes()

# Test round-trip
mulaw = pcm_16k_to_mulaw(test_pcm)
recovered_pcm = mulaw_to_pcm_16k(mulaw)

# Should be similar (some loss from compression)
assert len(recovered_pcm) == len(test_pcm)
```

### 3. Test STT Separately
```python
# Use working test file
audio_file = Path("tests/data/test_1_france_mono.wav")
with open(audio_file, "rb") as f:
    audio_data = f.read()[44:]  # Skip WAV header

# Send to STT
async with client.listen.v2.connect(...) as connection:
    await connection.send_media(audio_data)
    # Check for transcript
```

### 4. Profile Latency
```python
import time

start = time.time()
transcript = await stt.transcribe(audio)
logger.info(f"STT: {time.time() - start:.2f}s")

start = time.time()
response = await llm.complete(transcript)
logger.info(f"LLM: {time.time() - start:.2f}s")
```

---

## Next Steps for Code Improvements

1. **Add type hints everywhere** - Use `mypy` for static type checking
2. **Extract configuration** - Move hardcoded values to settings
3. **Add error handling** - Graceful degradation on provider failures
4. **Add metrics** - Track latency, errors, throughput
5. **Add tests for edge cases** - Empty audio, network failures, etc.
6. **Refactor VoiceSession** - Extract LLM/TTS logic to separate methods
7. **Add provider factory** - Support multiple providers via config
