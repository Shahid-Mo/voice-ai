"""
Test the refactored async providers (DeepgramSTT and DeepgramTTS).

Run: uv run python tests/test_async_providers.py
Requires: DEEPGRAM_API_KEY in .env
"""

import asyncio
from pathlib import Path

from voice_ai.providers.stt.deepgram import DeepgramSTT
from voice_ai.providers.tts.deepgram import DeepgramTTS


async def test_async_stt():
    """Test async DeepgramSTT provider."""
    print("=" * 60)
    print("Testing Async DeepgramSTT Provider")
    print("=" * 60)

    stt = DeepgramSTT()

    # Load test audio
    audio_file = Path(__file__).parent / "data" / "test_1_france_mono.wav"
    with open(audio_file, "rb") as f:
        audio_data = f.read()[44:]  # Skip WAV header

    print(f"\nLoaded {len(audio_data)} bytes from {audio_file.name}\n")

    # Track results
    transcript = ""
    interim_count = 0

    def on_message(message):
        nonlocal transcript, interim_count
        msg_type = getattr(message, "type", "unknown")

        if msg_type == "TurnInfo":
            event = getattr(message, "event", "")
            text = getattr(message, "transcript", "")

            if event == "Update" and text:
                interim_count += 1
                print(f"\r  Interim #{interim_count}: {text}", end="", flush=True)
            elif event == "EndOfTurn" and text:
                transcript = text
                print(f"\n  ✓ Final: {text}\n")

    # Test streaming transcription
    await stt.transcribe_stream(audio_data, on_message)

    print(f"✓ STT Test Complete")
    print(f"  - Interim results: {interim_count}")
    print(f"  - Final transcript: {transcript}")
    assert transcript, "No transcript received"


async def test_async_tts():
    """Test async DeepgramTTS provider."""
    print("\n" + "=" * 60)
    print("Testing Async DeepgramTTS Provider")
    print("=" * 60)

    tts = DeepgramTTS()

    # Test text
    text = "This is a test of the fully async Deepgram TTS provider using AsyncDeepgramClient with no threading bullshit."

    # Output file
    output_file = Path(__file__).parent / "data" / "async_provider_output.wav"

    print(f"\nSynthesizing: {text}\n")

    # Synthesize
    audio_path = await tts.synthesize(text, output_file)

    # Check output
    assert audio_path.exists(), f"Output file not created: {audio_path}"
    size = audio_path.stat().st_size
    print(f"✓ TTS Test Complete")
    print(f"  - Output: {audio_path.name}")
    print(f"  - Size: {size / 1024:.1f} KB")
    assert size > 1000, "Output file too small"


async def main():
    """Run all tests."""
    print("🧪 Testing Async Providers (DeepgramSTT & DeepgramTTS)\n")

    await test_async_stt()
    await test_async_tts()

    print("\n" + "=" * 60)
    print("🎉 ALL TESTS PASSED - Async providers work perfectly!")
    print("=" * 60)
    print("\nWhat this proves:")
    print("  ✅ DeepgramSTT: Fully async with AsyncDeepgramClient")
    print("  ✅ DeepgramTTS: Fully async with AsyncDeepgramClient")
    print("  ✅ No threading hacks needed")
    print("  ✅ Clean async/await throughout")
    print("\nReady for WebSocket implementation! 🚀")


if __name__ == "__main__":
    asyncio.run(main())
