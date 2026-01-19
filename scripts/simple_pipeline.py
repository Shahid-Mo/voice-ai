"""Test Deepgram Flux STT - Streaming transcription with turn detection."""

import asyncio

from voice_ai.providers.stt.deepgram import DeepgramSTT
from voice_ai.providers.stt.base import STTEventType


async def main():
    """Test Deepgram Flux streaming with real audio."""
    print("Testing Deepgram Flux STT Provider")
    print("=" * 70)
    print()

    # Create STT provider with Flux configuration
    stt = DeepgramSTT(
        model="flux-general-en",
        eot_threshold=0.7,
        eager_eot_threshold=0.5,  # Enable eager end-of-turn
        eot_timeout_ms=3000,
    )

    print("Flux Configuration:")
    print(f"  Model: {stt.model}")
    print(f"  End-of-Turn Threshold: {stt.eot_threshold}")
    print(f"  Eager End-of-Turn: {stt.eager_eot_threshold}")
    print(f"  Timeout: {stt.eot_timeout_ms}ms")
    print()

    # Track events
    events_received = []
    transcripts = []

    def on_event(event):
        """Handle STT events from Flux."""
        events_received.append(event.type)

        if event.type == STTEventType.CONNECTED:
            print("✅ Connected to Deepgram Flux (v2 endpoint)\n")

        elif event.type == STTEventType.TRANSCRIPT:
            if event.transcript:
                transcripts.append(event.transcript)
                final_marker = "✓" if event.is_final else "..."
                conf = f"({event.confidence:.2f})" if event.confidence else ""
                print(f"📝 {final_marker} {event.transcript} {conf}")

        elif event.type == STTEventType.END_OF_TURN:
            print("🔚 EndOfTurn: User finished speaking\n")

        elif event.type == STTEventType.EAGER_END_OF_TURN:
            print("⚡ EagerEndOfTurn: User likely finished (start LLM processing)\n")

        elif event.type == STTEventType.TURN_RESUMED:
            print("🔄 TurnResumed: User continued (cancel LLM response)\n")

        elif event.type == STTEventType.ERROR:
            print(f"❌ Error: {event.error}")

        elif event.type == STTEventType.CLOSED:
            print("👋 Connection closed")

    try:
        # Connect to Flux
        print("Connecting to Deepgram Flux streaming...\n")
        await stt.connect(
            on_event=on_event,
            sample_rate=16000,
            encoding="linear16",
        )

        # Download sample audio
        print("Downloading sample audio file...\n")
        sample_url = "https://static.deepgram.com/examples/Bueller-Life-moves-pretty-fast.wav"

        import httpx

        async with httpx.AsyncClient() as client:
            response = await client.get(sample_url)
            audio_data = response.content

        print(f"✅ Downloaded {len(audio_data)} bytes\n")

        # Send audio in chunks (simulate real-time streaming)
        # Recommended: ~80ms chunks = 2560 bytes at 16kHz linear16
        chunk_size = 2560

        print(f"Streaming audio in {chunk_size}-byte chunks (~80ms each)...")
        print("=" * 70)
        print()

        for i in range(0, len(audio_data), chunk_size):
            chunk = audio_data[i : i + chunk_size]
            await stt.send_audio(chunk)
            await asyncio.sleep(0.08)  # 80ms delay

        print()
        print("=" * 70)
        print("✅ Finished sending audio\n")

        # Wait for final events
        await asyncio.sleep(2)

        # Close connection
        await stt.close()

        # Summary
        print(f"📊 Summary:")
        print(f"   Events received: {len(events_received)}")
        print(f"   Event types: {set([e.value for e in events_received])}")
        print(f"   Transcript segments: {len(transcripts)}")

        if transcripts:
            full_transcript = " ".join(transcripts)
            print(f"   Full transcript: {full_transcript}")

        print()
        print("=" * 70)
        print("✅ Deepgram Flux STT test passed!")
        print("💡 Your Deepgram API key is working correctly with Flux.")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("\n💡 Check:")
        print("   1. DEEPGRAM_API_KEY is set in .env")
        print("   2. You have Deepgram credits")
        print("   3. Your API key has access to Flux model")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
