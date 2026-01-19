"""Test Deepgram Aura TTS provider."""
import asyncio
import os
import struct

from voice_ai.providers.tts.deepgram import DeepgramTTS


async def main():
    print("Testing Deepgram Aura TTS")
    print("=" * 50)

    tts = DeepgramTTS(default_voice="phoebe", sample_rate=16000, encoding="linear16")

    text = "Hello! This is a test of the Deepgram Aura text to speech system. How does it sound?"

    print(f"\nSynthesizing: '{text}'")
    result = await tts.synthesize(text)

    print(f"✓ Generated {len(result.audio_data)} bytes of audio")
    print(f"  Sample rate: {result.sample_rate} Hz")
    print(f"  Format: {result.format}")

    # Save as WAV
    os.makedirs("audio/responses", exist_ok=True)
    output_file = "audio/responses/test_tts.wav"

    # Create WAV header
    wav_header = struct.pack(
        '<4sI4s4sIHHIIHH4sI',
        b'RIFF', 36 + len(result.audio_data), b'WAVE', b'fmt ', 16, 1, 1,
        result.sample_rate, result.sample_rate * 2, 2, 16, b'data', len(result.audio_data)
    )

    with open(output_file, 'wb') as f:
        f.write(wav_header + result.audio_data)

    print(f"✓ Saved to {output_file}")
    print("\n" + "=" * 50)
    print("✓ TTS test complete!")


if __name__ == "__main__":
    asyncio.run(main())
