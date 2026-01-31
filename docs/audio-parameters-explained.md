# Audio Parameters Explained

## Overview

Our Deepgram STT implementation uses specific audio parameters optimized for voice AI applications. This doc explains why we chose these values.

## The Parameters

```python
encoding: str = "linear16"
sample_rate: int = 16000
chunk_size: int = 4096
```

---

## Encoding: `linear16`

**What it is:** Raw PCM (Pulse Code Modulation) audio with 16-bit samples.

**Why this encoding:**
- ✅ **Industry standard** for telephony and voice AI
- ✅ **No compression** = no quality loss
- ✅ **Universal support** across all audio systems
- ✅ **Deterministic size:** Easy to calculate buffer sizes and timing
- ✅ **Low CPU overhead:** No decoding needed

**Format details:**
- 16 bits per sample = 2 bytes per sample
- Signed integer format (-32768 to +32767)
- Little-endian byte order (standard)

**Alternatives:**
| Encoding | Use Case | Trade-off |
|----------|----------|-----------|
| `linear32` | High-fidelity recording | 2x bandwidth, no accuracy gain for speech |
| `mulaw` | Legacy telephony | Compressed but lower quality |
| `opus` | Bandwidth-constrained apps | Compressed but adds encoding latency |

**Raw vs Containerized Audio Formats:**

When working with audio, you have two choices:

1. **Raw Audio (what we use):**
   - Pure audio samples, no headers or metadata
   - Just bytes: `[sample1][sample2][sample3]...`
   - Example: `linear16` encoding = raw PCM data
   - File extension: `.pcm`, `.raw` (or no extension)

2. **Containerized Audio:**
   - Audio data wrapped in a file format with headers
   - Structure: `[header][metadata][audio data][footer]`
   - Examples: `.wav`, `.ogg`, `.mp3`, `.flac`

**Why we use raw for streaming:**

| Aspect | Raw (linear16) | Containerized (WAV) |
|--------|----------------|---------------------|
| **Headers** | None - pure audio | Yes - header describes format |
| **Streaming** | ✅ Send any chunk size | ❌ Must send valid container chunks |
| **Overhead** | 0 bytes per chunk | ~44 bytes (WAV header) per file |
| **Timing control** | ✅ Precise (4096 bytes = exactly 128ms) | ❌ Must account for header offset |
| **Deepgram support** | ✅ Preferred for real-time | ✅ Supported but adds parsing overhead |

**Example: Sending 10 seconds of audio**

```python
# Raw (linear16): Send pure audio
chunk = audio_data[0:4096]  # Exactly 128ms of audio
connection.send_media(chunk)

# Containerized (WAV): Must handle header
wav_file = add_wav_header(audio_data)
# First chunk includes 44-byte header
# chunk[0:44] = WAV header (not audio!)
# chunk[44:4096] = only 4052 bytes of audio (126.6ms)
connection.send_media(wav_file[0:4096])  # ❌ Timing is off
```

**When to use containerized formats:**
- Saving to disk (WAV/FLAC for quality, MP3/Ogg for size)
- Sharing audio files between applications
- Playback in media players
- When you need to store metadata (artist, title, duration)

**When to use raw formats:**
- Real-time streaming (our use case)
- When you need precise timing control
- Low-latency applications
- When both sides already know the format (sample rate, encoding)

---

## Sample Rate: `16000` Hz (16 kHz)

**What it is:** Number of audio samples captured per second.

**Why 16 kHz:**
- ✅ **Deepgram's recommendation** (see docs: "Required 16000 recommended")
- ✅ **Telephony standard:** PSTN, VoIP all use 8-16 kHz
- ✅ **Voice-optimized:** Human speech fundamental frequencies are 80-300 Hz (male) and 165-255 Hz (female). By Nyquist theorem, 16 kHz captures up to 8 kHz frequency range, which is more than enough for intelligible speech.
- ✅ **Bandwidth efficient:** Half the data of 32 kHz, no quality loss for speech

**The math:**
```
Sample rate: 16,000 samples/sec
Encoding: linear16 (2 bytes/sample)
Data rate: 16,000 × 2 = 32,000 bytes/sec = 32 KB/s
```

**Alternatives:**
| Sample Rate | Use Case | Trade-off |
|-------------|----------|-----------|
| `8000` Hz | Legacy phone systems | Lower quality, acceptable for basic speech |
| `24000` Hz | High-quality voice assistants | 1.5x bandwidth, marginal quality improvement |
| `44100` Hz | Music/consumer audio | 2.75x bandwidth, overkill for speech |
| `48000` Hz | Professional audio/video | 3x bandwidth, unnecessary for voice AI |

**Why NOT use higher sample rates?**
- Speech doesn't contain meaningful information above 8 kHz
- Higher rates = more bandwidth, storage, processing cost
- No accuracy improvement for STT models trained on voice

---

## Chunk Size: `4096` bytes

**What it is:** Number of bytes sent to Deepgram in each network call.

**Why 4096 bytes:**
- ✅ **128ms of audio:** Matches natural speech segment timing
- ✅ **Low latency:** Fast enough for real-time transcription
- ✅ **Network efficient:** Not too small (overhead) or too large (buffering)
- ✅ **Turn detection:** Allows Flux to detect pauses and EndOfTurn events

**The math:**
```
chunk_size = 4096 bytes
sample_rate = 16000 Hz
bytes_per_sample = 2 (linear16)

bytes_per_second = 16000 × 2 = 32,000 bytes/sec
chunk_duration = 4096 / 32,000 = 0.128 seconds = 128ms

Result: Each chunk represents 128ms of audio
```

**Why 128ms chunks?**
- Human speech segments typically 100-200ms
- Fast enough to feel "instant" (sub-150ms perception threshold)
- Enough data for Deepgram to process phonemes and detect pauses
- Matches typical WebRTC packet sizes

**Alternatives:**
| Chunk Size | Duration | Use Case | Trade-off |
|------------|----------|----------|-----------|
| `1024` bytes | 32ms | Ultra-low latency | Too much HTTP overhead |
| `2048` bytes | 64ms | Low latency gaming | More network calls |
| `8192` bytes | 256ms | Batch processing | Slower turn detection |
| `16384` bytes | 512ms | Non-real-time apps | Poor user experience |

**Impact on turn detection:**
```
Small chunks (1024):  Faster pause detection, more network overhead
Medium chunks (4096): ✅ Optimal balance
Large chunks (16384): Slower pause detection, fewer network calls
```

---

## Real-World Example

**Scenario:** 10-second voice message

```
Duration: 10 seconds
Sample rate: 16000 Hz
Encoding: linear16 (2 bytes/sample)

Total bytes: 10 sec × 16000 samples/sec × 2 bytes/sample = 320,000 bytes (312.5 KB)

Chunk size: 4096 bytes
Number of chunks: 320,000 / 4096 ≈ 78 chunks
Time between chunks: 128ms

Network calls: 78 HTTP requests over 10 seconds
Data rate: 32 KB/s (256 kbps) - similar to phone call bandwidth
```

---

## Quick Reference Table

| Parameter | Value | Calculation | Result |
|-----------|-------|-------------|--------|
| **Encoding** | `linear16` | 16 bits/sample | 2 bytes/sample |
| **Sample Rate** | `16000` Hz | 16000 samples/sec | Industry standard for speech |
| **Bytes per Second** | - | 16000 × 2 | 32,000 bytes/sec |
| **Chunk Size** | `4096` bytes | - | 128ms of audio |
| **Chunk Duration** | - | 4096 / 32000 | 0.128 seconds |

---

## When to Change These Values

**Use 8000 Hz if:**
- Integrating with legacy phone systems (PSTN)
- Extremely bandwidth-constrained environment
- Acceptable to sacrifice some clarity for efficiency

**Use 24000+ Hz if:**
- High-fidelity voice recording (podcasts, broadcasting)
- Music analysis (not speech-to-text)
- You need to preserve audio quality for playback

**Use smaller chunks (2048) if:**
- Building ultra-low-latency applications (e.g., real-time translation)
- Network is reliable and can handle more frequent requests

**Use larger chunks (8192) if:**
- Processing pre-recorded audio (not live streaming)
- Network reliability is poor (reduce number of requests)
- Turn detection is not critical

---

## References

- [Deepgram Audio Format Requirements](https://developers.deepgram.com/docs/flux/quickstart#audio-format-requirements)
- [Deepgram recommends 16000 Hz for best accuracy](https://developers.deepgram.com/docs/flux/quickstart#audio-format-requirements)
- Nyquist-Shannon Sampling Theorem: Sample rate must be ≥2× highest frequency
- Human speech frequency range: 80-8000 Hz (fundamental + harmonics)
