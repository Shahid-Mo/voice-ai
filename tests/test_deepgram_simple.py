"""
Simple test for Deepgram STT.

Run: uv run python tests/test_deepgram_simple.py
Requires: DEEPGRAM_API_KEY in .env
"""

import time
from pathlib import Path

from voice_ai.providers.stt.deepgram import DeepgramSTT


def on_message(message):
    """Print all messages from Deepgram."""
    msg_type = getattr(message, "type", "unknown")

    # DEBUG: Print ALL messages
    print(f"[DEBUG] Message type: {msg_type}")
    if hasattr(message, "__dict__"):
        print(f"[DEBUG] Message content: {message.__dict__}")

    if msg_type == "Connected":
        print("✓ Connected to Deepgram Flux\n")

    elif msg_type == "TurnInfo":
        event = getattr(message, "event", "")
        transcript = getattr(message, "transcript", "")

        if event == "Update" and transcript:
            print(f"\r  Interim: {transcript}", end="", flush=True)

        elif event == "EndOfTurn" and transcript:
            print(f"\n✓ Final: {transcript}\n")


def main():
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
    stt.connect(on_message=on_message, encoding="linear16", sample_rate=16000)

    print("Sending audio...")

    # Send in chunks at real-time speed
    # At 16kHz mono linear16: 32000 bytes/sec
    # 4096 bytes = 0.128 seconds of audio
    chunk_size = 4096
    chunk_duration = chunk_size / 32000.0  # 0.128 seconds

    for i in range(0, len(audio_data), chunk_size):
        stt.send_audio(audio_data[i:i + chunk_size])
        time.sleep(chunk_duration)

    # Wait a bit longer for final processing
    print("Waiting for final transcript...\n")
    time.sleep(3)

    stt.close()
    print("✓ Done")


if __name__ == "__main__":
    main()
