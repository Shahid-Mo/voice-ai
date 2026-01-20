"""
Simple async test for Deepgram STT.

Run: uv run python tests/test_deepgram_simple.py
Requires: DEEPGRAM_API_KEY in .env
"""

import asyncio
from pathlib import Path
from typing import Any

from voice_ai.providers.stt.deepgram import DeepgramSTT


def on_message(message: Any) -> None:
    """Print all messages from Deepgram."""
    msg_type = getattr(message, "type", "unknown")

    if msg_type == "Connected":
        print("✓ Connected to Deepgram Flux\n")

    elif msg_type == "TurnInfo":
        event = getattr(message, "event", "")
        transcript = getattr(message, "transcript", "")

        if event == "Update" and transcript:
            # Interim transcript - overwrites previous line
            print(f"\r  Interim: {transcript}", end="", flush=True)

        elif event == "EndOfTurn" and transcript:
            # Final transcript - move to new line
            print(f"\n✓ Final: {transcript}\n")


async def main():
    """Test with actual audio file."""
    print("Testing Deepgram STT with audio file...\n")

    # Read test audio (mono version)
    audio_file = Path(__file__).parent / "data" / "stt_test_mono.wav"

    if not audio_file.exists():
        print(f"✗ Audio file not found: {audio_file}")
        return

    print(f"Reading {audio_file.name}...")
    with open(audio_file, "rb") as f:
        audio_data = f.read()

    # Skip WAV header (first 44 bytes) since we're telling Deepgram it's raw linear16
    audio_data = audio_data[44:]

    print(f"✓ Loaded {len(audio_data)} bytes (header stripped)\n")

    # Connect and transcribe
    stt = DeepgramSTT()

    print("Streaming audio to Deepgram...\n")

    await stt.transcribe_stream(
        audio_data=audio_data,
        on_message=on_message,
        encoding="linear16",
        sample_rate=16000,
        chunk_size=4096,
    )

    print("✓ Done")


if __name__ == "__main__":
    asyncio.run(main())
