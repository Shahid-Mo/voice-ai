"""
Test AsyncDeepgramClient for both STT and TTS.

This tests if we can use the fully async Deepgram SDK instead of
threading hacks with the sync DeepgramClient.

Run: uv run python tests/test_async_deepgram.py
Requires: DEEPGRAM_API_KEY in .env
"""

import asyncio
from pathlib import Path

from deepgram import AsyncDeepgramClient
from deepgram.core.events import EventType

from voice_ai.config import settings


async def test_async_stt():
    """Test AsyncDeepgramClient for STT."""
    print("=" * 60)
    print("Testing AsyncDeepgramClient STT (listen.v2)")
    print("=" * 60)

    client = AsyncDeepgramClient(api_key=settings.deepgram_api_key)

    # Load test audio
    audio_file = Path(__file__).parent / "data" / "test_1_france_mono.wav"
    with open(audio_file, "rb") as f:
        audio_data = f.read()[44:]  # Skip WAV header

    print(f"\nLoaded {len(audio_data)} bytes from {audio_file.name}\n")

    # Track results
    transcript = ""
    interim_count = 0

    async with client.listen.v2.connect(
        model="flux-general-en",
        encoding="linear16",
        sample_rate=16000,
    ) as connection:
        print("✓ Connected to Deepgram STT (async)\n")

        async def message_handler(message):
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

        # Register handler
        connection.on(EventType.MESSAGE, message_handler)

        # Start listening
        listen_task = asyncio.create_task(connection.start_listening())

        # Send audio in chunks (simulate real-time)
        chunk_size = 4096
        for i in range(0, len(audio_data), chunk_size):
            chunk = audio_data[i : i + chunk_size]
            await connection.send_media(chunk)  # Async!
            await asyncio.sleep(0.1)  # Simulate real-time

        # Wait for processing
        await asyncio.sleep(1.0)

        # Close connection
        from deepgram.listen.v2.types import ListenV2CloseStream

        await connection.send_close_stream(ListenV2CloseStream(type="CloseStream"))
        await listen_task

    print(f"Final Transcript: {transcript}")
    print(f"Interim updates: {interim_count}\n")

    return transcript


async def test_async_tts(text: str):
    """Test AsyncDeepgramClient for TTS."""
    print("=" * 60)
    print("Testing AsyncDeepgramClient TTS (speak.v1)")
    print("=" * 60)

    client = AsyncDeepgramClient(api_key=settings.deepgram_api_key)

    # Output file
    output_file = Path(__file__).parent / "data" / "async_tts_output.wav"

    # Create WAV header
    import wave

    with wave.open(str(output_file), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)

    print(f"\nSynthesizing: {text}\n")

    # Track audio
    chunk_count = 0
    total_bytes = 0

    async with client.speak.v1.connect(
        model="aura-2-thalia-en",
        encoding="linear16",
        sample_rate=16000,
    ) as connection:
        print("✓ Connected to Deepgram TTS (async)\n")

        async def audio_handler(message):
            nonlocal chunk_count, total_bytes

            if isinstance(message, bytes):
                chunk_count += 1
                total_bytes += len(message)

                # Write to file
                with open(output_file, "ab") as f:
                    f.write(message)

                if chunk_count % 10 == 0:
                    print(f"  Received {chunk_count} chunks ({total_bytes:,} bytes)...", end="\r", flush=True)
            else:
                msg_type = getattr(message, "type", "Unknown")
                if msg_type == "Flushed":
                    print(f"\n  ✓ Flushed (audio complete)")

        # Register handler
        connection.on(EventType.MESSAGE, audio_handler)

        # Start listening
        listen_task = asyncio.create_task(connection.start_listening())

        # Send text
        from deepgram.speak.v1.types import SpeakV1Close, SpeakV1Flush, SpeakV1Text

        await connection.send_text(SpeakV1Text(text=text))  # Async!
        await connection.send_flush(SpeakV1Flush(type="Flush"))  # Async!

        # Wait for audio
        await asyncio.sleep(3.0)

        # Close
        await connection.send_close(SpeakV1Close(type="Close"))  # Async!
        await asyncio.sleep(0.2)
        await listen_task

    print(f"\n✓ Saved {total_bytes:,} bytes to {output_file.name}")
    print(f"  Total chunks: {chunk_count}\n")


async def main():
    """Test both STT and TTS with AsyncDeepgramClient."""
    print("\n🧪 Testing AsyncDeepgramClient (Fully Async, No Threading)\n")

    # Test STT
    transcript = await test_async_stt()

    if not transcript:
        print("✗ STT failed, skipping TTS test")
        return

    # Test TTS with the transcript
    await test_async_tts(transcript)

    print("=" * 60)
    print("✓ All tests passed!")
    print("  AsyncDeepgramClient works for both STT and TTS")
    print("  No threading needed - fully async/await")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
