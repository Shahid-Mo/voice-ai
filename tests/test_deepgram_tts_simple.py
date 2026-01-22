"""
Simple async test for Deepgram TTS.

Run: uv run python tests/test_deepgram_tts_simple.py
Requires: DEEPGRAM_API_KEY in .env
"""

import asyncio
from pathlib import Path

from voice_ai.providers.tts.deepgram import DeepgramTTS

TTS_TEXT = "Hello, this is a text to speech example using Deepgram. How are you doing today? I am fine thanks for asking."


async def main():
    """Test TTS with streaming to file."""
    print("Testing Deepgram TTS with Aura 2...\n")

    # Initialize TTS
    tts = DeepgramTTS()

    # Output file path
    output_dir = Path(__file__).parent / "data"
    output_dir.mkdir(exist_ok=True)
    output_file = output_dir / "tts_test.wav"

    print(f"Synthesizing text to {output_file.name}...\n")
    print(f"Text: {TTS_TEXT}\n")

    # Synthesize to file
    audio_path = await tts.synthesize(
        text=TTS_TEXT,
        output_file=output_file,
        model="aura-2-thalia-en",
        encoding="linear16",
        sample_rate=16000,
    )

    print(f"\n✓ Audio saved to {audio_path}")
    print(f"  File size: {audio_path.stat().st_size} bytes")

    # Test streaming with callback
    print("\nTesting streaming with callback...")

    stream_file = output_dir / "tts_test_stream.wav"
    chunk_count = 0

    def on_audio(chunk: bytes) -> None:
        nonlocal chunk_count
        chunk_count += 1
        if chunk_count == 1:
            print("  ✓ Receiving audio chunks...")

    await tts.synthesize_stream(
        text=TTS_TEXT,
        on_audio=on_audio,
        model="aura-2-thalia-en",
    )

    print(f"  ✓ Received {chunk_count} audio chunks")
    print("\n✓ Done")


if __name__ == "__main__":
    asyncio.run(main())
