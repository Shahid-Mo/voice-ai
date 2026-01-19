"""Test Deepgram Flux STT provider."""
import asyncio

from voice_ai.providers.stt.deepgram import DeepgramSTT
from voice_ai.providers.stt.base import STTEventType


async def main():
    print("Testing Deepgram Flux STT")
    print("=" * 50)

    stt = DeepgramSTT(
        model="flux-general-en",
        eot_threshold=0.7,
        eager_eot_threshold=0.5,
    )

    events = []
    transcript_parts = []

    def on_event(event):
        events.append(event)
        if event.type == STTEventType.CONNECTED:
            print("✓ Connected to Deepgram Flux")
        elif event.type == STTEventType.TRANSCRIPT:
            if event.transcript:
                transcript_parts.append(event.transcript)
                print(f"  {event.transcript}")
        elif event.type == STTEventType.END_OF_TURN:
            print("✓ End of turn detected")
        elif event.type == STTEventType.ERROR:
            print(f"✗ Error: {event.error}")

    # Connect and stream audio
    print("\nConnecting...")
    await stt.connect(on_event=on_event, sample_rate=16000, encoding="linear16")

    # Download sample audio
    print("Downloading sample audio...")
    import httpx
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://static.deepgram.com/examples/Bueller-Life-moves-pretty-fast.wav"
        )
        audio_data = response.content

    print(f"Streaming {len(audio_data)} bytes\n")

    # Stream in chunks
    chunk_size = 2560  # ~80ms at 16kHz
    for i in range(0, len(audio_data), chunk_size):
        await stt.send_audio(audio_data[i:i + chunk_size])
        await asyncio.sleep(0.08)

    # Wait for processing
    await asyncio.sleep(2)
    await stt.close()

    print("\n" + "=" * 50)
    print(f"Events received: {len(events)}")
    print(f"Full transcript: {' '.join(transcript_parts)}")
    print("✓ STT test complete!")


if __name__ == "__main__":
    asyncio.run(main())
