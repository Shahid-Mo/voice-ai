# Chunk Size: A Hyperparameter for Voice AI

## The Honest Truth

**We don't know the optimal chunk size for our application yet.** It depends on:

1. Network conditions (latency, jitter, packet loss)
2. Your specific use case (live conversation vs. transcription)
3. How aggressive you want turn detection to be
4. Trade-offs between latency and network overhead

This is a **hyperparameter** - a tunable configuration value that affects system performance but must be determined empirically through testing.

---

## What Deepgram Actually Says

From their official docs:

```python
# Note: 1024 bytes = ~32ms of audio at 16kHz linear16
# For optimal performance, consider using ~2560 bytes (~80ms at 16kHz)
```

**Deepgram recommends 80ms chunks (2560 bytes), not 128ms (4096 bytes).**

So why did we use 4096? **No good reason.** It's a common buffer size (2^12), but that's arbitrary.

---

## The Trade-off Space

```
Smaller chunks (32ms)          Larger chunks (256ms)
        │                              │
        ▼                              ▼
   Lower latency                Higher latency
   More network calls           Fewer network calls
   Better turn detection        Slower turn detection
   More HTTP overhead           Less HTTP overhead
   Higher CPU usage            Lower CPU usage
```

There's no "correct" answer - only trade-offs.

---

## Hyperparameter Candidates

Based on Deepgram docs and common practice:

| Chunk Size | Duration @ 16kHz | Use Case | Pros | Cons |
|------------|------------------|----------|------|------|
| **1024 bytes** | 32ms | Ultra-low latency | Fastest response | 🔴 High network overhead |
| **2560 bytes** | 80ms | ✅ **Deepgram recommended** | Balanced performance | Need to test |
| **4096 bytes** | 128ms | Our current default | Common buffer size (2^12) | Arbitrary choice |
| **8192 bytes** | 256ms | Batch processing | Efficient networking | 🔴 Slow turn detection |

---

## What "Natural Speech Segment Timing" Actually Means

I claimed 128ms "matches natural speech segment timing." That was speculative. Here are the real linguistics:

**Phonemes (speech sounds):**
- Duration: 20-100ms
- Example: "cat" = /k/ (30ms) + /æ/ (80ms) + /t/ (20ms)

**Syllables:**
- Duration: 100-300ms
- Example: "hel-lo" = ~200ms each

**Pauses in speech:**
- Short pause (between words): 100-200ms
- Phrase boundary: 200-400ms
- Sentence boundary: 400-800ms

**Implications:**
- **32ms chunks:** Sub-phoneme level, might catch partial sounds
- **80ms chunks:** ~1 phoneme, good granularity
- **128ms chunks:** ~1-2 phonemes, still reasonable
- **256ms chunks:** Full syllable, may miss quick pauses

**But:** Deepgram's ML model has internal buffering and context windows. The chunk size affects *network latency* more than *transcription accuracy*.

---

## How to Find the Optimal Value

This is the engineering approach:

### 1. Define Your Metrics

```python
class ChunkSizeMetrics:
    latency_ms: float           # Time from speech to transcript
    network_calls: int          # Total HTTP requests
    turn_detection_accuracy: float  # % of correct EndOfTurn events
    bandwidth_mbps: float       # Network usage
    cpu_percent: float          # Processing overhead
```

### 2. Benchmark Different Values

```python
CHUNK_SIZES_TO_TEST = [
    1024,   # 32ms - Deepgram's minimum example
    2560,   # 80ms - Deepgram's recommendation
    4096,   # 128ms - Our arbitrary default
    8192,   # 256ms - Larger chunks
]

for chunk_size in CHUNK_SIZES_TO_TEST:
    metrics = test_chunk_size(
        audio_file="test_conversation.wav",
        chunk_size=chunk_size,
    )
    print(f"{chunk_size} bytes: {metrics}")
```

### 3. Test with Real Use Cases

**Test Case 1: Quick interruptions (barge-in)**
- User says: "Hey assistant, play music... wait no, nevermind"
- Metric: Did EndOfTurn fire after "wait no"?

**Test Case 2: Long monologue**
- User speaks for 60 seconds continuously
- Metric: Network calls, bandwidth, CPU usage

**Test Case 3: Stuttering/hesitation**
- User says: "Um... I need... uh... the report"
- Metric: Did it wait for actual end-of-turn?

### 4. Profile in Production

```python
# Add telemetry to your STT provider
async def transcribe_stream(self, audio_data, chunk_size):
    start_time = time.time()
    network_calls = 0

    for chunk in chunks:
        await send_chunk(chunk)
        network_calls += 1

    latency = time.time() - start_time
    log_metrics({
        "chunk_size": chunk_size,
        "latency": latency,
        "network_calls": network_calls,
    })
```

---

## Is This a "Hyperparameter"?

Yes, in the general sense:

**Machine Learning Hyperparameters:**
- Learning rate, batch size, number of layers
- Not learned by the model, set by the engineer
- Tuned through experimentation (grid search, Bayesian optimization)

**Systems Engineering Hyperparameters:**
- Chunk size, buffer sizes, thread pool sizes
- Not determined by the system, set by the developer
- Tuned through benchmarking and profiling

**Similarities:**
1. **No analytical solution:** Can't mathematically derive the "correct" value
2. **Performance impact:** Dramatically affects results
3. **Context-dependent:** Optimal value depends on your specific use case
4. **Empirical tuning:** Must test multiple values and measure

**The process is the same:**
1. Define a search space (1024, 2560, 4096, 8192)
2. Define metrics (latency, accuracy, overhead)
3. Test systematically
4. Pick the value that optimizes your objective function

---

## Recommendation: Start with Deepgram's Suggestion

**Until we benchmark, use `chunk_size = 2560` (80ms).**

Why?
1. ✅ Deepgram explicitly recommends it
2. ✅ They've tested it with their own infrastructure
3. ✅ Balances latency and overhead
4. ❌ Our 4096 (128ms) was an arbitrary choice

**Updated code:**

```python
async def transcribe_stream(
    self,
    audio_data: bytes,
    on_message: Callable[[Any], None],
    model: str = "flux-general-en",
    encoding: str = "linear16",
    sample_rate: int = 16000,
    chunk_size: int = 2560,  # ✅ Changed from 4096 to match Deepgram recommendation
) -> None:
```

---

## Future Work: Make It Configurable

Since this is a hyperparameter, we should allow users to tune it:

```python
# Config file or environment variable
STT_CHUNK_SIZE=2560  # Default to Deepgram recommendation

# Make it easy to A/B test
stt = DeepgramSTT()
await stt.transcribe_stream(
    audio_data,
    on_message,
    chunk_size=settings.stt_chunk_size,  # Configurable
)
```

Then we can run experiments in production with different values and see which performs best for our specific use case.

---

## Summary

**What I got wrong:**
- Claimed 128ms (4096 bytes) was optimal without evidence
- Used vague reasoning like "matches speech timing" instead of data

**What we actually know:**
- Deepgram recommends 80ms (2560 bytes)
- Chunk size is a hyperparameter that must be tuned empirically
- There's a trade-off between latency, network overhead, and turn detection

**What we should do:**
1. Change default from 4096 → 2560 (follow Deepgram's recommendation)
2. Make it configurable so we can experiment
3. Add telemetry to measure performance in production
4. Benchmark different values with real use cases

**The honest answer:** We won't know the "best" chunk size until we test it with real traffic patterns and measure the outcomes.
