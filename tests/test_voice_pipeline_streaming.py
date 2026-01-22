"""
Streaming voice pipeline test with sentence-by-sentence TTS.

Tests STT → LLM → TTS with incremental audio synthesis.
LLM tokens are buffered into sentences and synthesized immediately.

Run: uv run python tests/test_voice_pipeline_streaming.py
Requires: DEEPGRAM_API_KEY and OPENAI_API_KEY in .env
"""l

import asyncio
import re
import threading
from pathlib import Path
from typing import Any

from deepgram import DeepgramClient
from deepgram.core.events import EventType
from deepgram.speak.v1.types import SpeakV1Close, SpeakV1Flush, SpeakV1Text

from voice_ai.config import settings
from voice_ai.providers.llm.openai import OpenAILLM
from voice_ai.providers.stt.deepgram import DeepgramSTT


def ends_with_sentence_boundary(text: str) -> bool:
    """Check if text ends with sentence punctuation."""
    return bool(re.search(r'[.!?]\s*$', text))


async def main():
    """Test streaming voice pipeline with incremental TTS."""
    print("=== Streaming Voice AI Pipeline Test ===\n")

    # Setup providers
    stt = DeepgramSTT()
    llm = OpenAILLM(model="gpt-5-nano")
    tts_client = DeepgramClient(api_key=settings.deepgram_api_key)

    # Input audio file
    audio_file = Path(__file__).parent / "data" / "test_1_france_mono.wav"

    if not audio_file.exists():
        print(f"✗ Audio file not found: {audio_file}")
        return

    print(f"📁 Input: {audio_file.name}\n")

    # Step 1: STT - Transcribe audio
    print("🎤 Step 1: Transcribing audio...\n")

    with open(audio_file, "rb") as f:
        audio_data = f.read()[44:]  # Skip WAV header

    transcript = ""

    def on_stt_message(message: Any) -> None:
        nonlocal transcript
        msg_type = getattr(message, "type", "unknown")

        if msg_type == "Connected":
            print("  ✓ Connected to Deepgram STT\n")
        elif msg_type == "TurnInfo":
            event = getattr(message, "event", "")
            text = getattr(message, "transcript", "")

            if event == "Update" and text:
                print(f"\r  Interim: {text}", end="", flush=True)
            elif event == "EndOfTurn" and text:
                transcript = text
                print(f"\n  ✓ Final: {text}\n")

    await stt.transcribe_stream(
        audio_data=audio_data,
        on_message=on_stt_message,
        encoding="linear16",
        sample_rate=16000,
        chunk_size=4096,
    )

    if not transcript:
        print("✗ No transcript received")
        return

    # Step 2: LLM → TTS Streaming Pipeline
    print("🤖 Step 2: Streaming LLM → TTS pipeline...\n")

    # Create conversation
    conversation_id = await llm.create_conversation()
    print(f"  ✓ Created conversation: {conversation_id}\n")
    print(f"  User: {transcript}")
    print("  Assistant: ", end="", flush=True)

    # Setup output file
    output_dir = Path(__file__).parent / "data"
    output_file = output_dir / "pipeline_streaming_output.wav"

    # Create WAV header
    import wave

    with wave.open(str(output_file), "wb") as wav:
        wav.setnchannels(1)  # Mono
        wav.setsampwidth(2)  # 16-bit
        wav.setframerate(16000)

    # Track metrics
    sentences_synthesized = 0
    total_audio_bytes = 0
    audio_chunks_received = 0

    # Open persistent TTS connection
    with tts_client.speak.v1.connect(
        model="aura-2-thalia-en",
        encoding="linear16",
        sample_rate=16000,
    ) as tts_connection:

        # Track when audio is being received (use threading.Event for sync callback)
        audio_ready = threading.Event()

        def on_tts_message(message: Any) -> None:
            nonlocal total_audio_bytes, audio_chunks_received

            if isinstance(message, bytes):
                # Audio chunk received
                audio_chunks_received += 1
                total_audio_bytes += len(message)

                # Write to file
                with open(output_file, "ab") as f:
                    f.write(message)
            else:
                msg_type = getattr(message, "type", "Unknown")
                if msg_type == "Flushed":
                    # Signal that this sentence's audio is complete
                    audio_ready.set()

        # Register TTS event handler
        tts_connection.on(EventType.MESSAGE, on_tts_message)

        # Start TTS listening thread
        threading.Thread(target=tts_connection.start_listening, daemon=True).start()

        # Stream LLM tokens and synthesize incrementally
        sentence_buffer = ""
        llm_response = ""

        async for llm_chunk in llm.stream_complete(
            input=transcript,
            conversation_id=conversation_id,
        ):
            print(llm_chunk, end="", flush=True)
            llm_response += llm_chunk
            sentence_buffer += llm_chunk

            # Check if we have a complete sentence
            if ends_with_sentence_boundary(sentence_buffer):
                sentences_synthesized += 1

                # Send sentence to TTS immediately
                tts_connection.send_text(SpeakV1Text(text=sentence_buffer.strip()))

                # Flush to get audio NOW
                tts_connection.send_flush(SpeakV1Flush(type="Flush"))

                print(f" [🔊 Sentence {sentences_synthesized}]", end="", flush=True)

                # Wait for audio to be received (run blocking wait in thread pool)
                audio_ready.clear()
                try:
                    await asyncio.to_thread(audio_ready.wait, 10.0)
                except Exception:
                    print(" [⚠️  Audio timeout]", end="", flush=True)

                sentence_buffer = ""

        # Handle any remaining text (incomplete sentence)
        if sentence_buffer.strip():
            sentences_synthesized += 1
            tts_connection.send_text(SpeakV1Text(text=sentence_buffer.strip()))
            tts_connection.send_flush(SpeakV1Flush(type="Flush"))

            print(f" [🔊 Final chunk]", end="", flush=True)

            audio_ready.clear()
            try:
                await asyncio.to_thread(audio_ready.wait, 10.0)
            except Exception:
                pass

        print("\n")

        # Close TTS connection
        tts_connection.send_close(SpeakV1Close(type="Close"))
        await asyncio.sleep(0.2)

    # Summary
    print("=" * 70)
    print("✓ Streaming pipeline complete!")
    print(f"  Input:  {audio_file.name}")
    print(f"  Output: {output_file.name} ({total_audio_bytes:,} bytes)")
    print(f"  Transcript: {transcript}")
    print(f"  Response: {llm_response}")
    print(f"  Sentences synthesized: {sentences_synthesized}")
    print(f"  Audio chunks received: {audio_chunks_received}")
    print(f"  Average latency: Sentence-by-sentence (incremental)")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
