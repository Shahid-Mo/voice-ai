"""
Scrappy test for full voice pipeline: STT → LLM → TTS

Takes audio input, transcribes it, gets LLM response, synthesizes response to audio.

Run: uv run python tests/test_voice_pipeline.py
Requires: DEEPGRAM_API_KEY and OPENAI_API_KEY in .env
"""

import asyncio
from pathlib import Path
from typing import Any

from voice_ai.providers.llm.openai import OpenAILLM
from voice_ai.providers.stt.deepgram import DeepgramSTT
from voice_ai.providers.tts.deepgram import DeepgramTTS


async def main():
    """Test full voice pipeline."""
    print("=== Voice AI Pipeline Test ===\n")

    # Setup providers
    stt = DeepgramSTT()
    llm = OpenAILLM(model="gpt-5-nano")
    tts = DeepgramTTS()

    # Input audio file (mono WAV)
    audio_file = Path(__file__).parent / "data" / "test_1_france_mono.wav"

    if not audio_file.exists():
        print(f"✗ Audio file not found: {audio_file}")
        print("  Run ffmpeg to convert first:")
        print(f"  ffmpeg -i tests/data/test_1_france.m4a -ar 16000 -ac 1 -c:a pcm_s16le {audio_file} -y")
        return

    print(f"📁 Input: {audio_file.name}\n")

    # Step 1: STT - Transcribe audio
    print("🎤 Step 1: Transcribing audio with Deepgram STT...")

    with open(audio_file, "rb") as f:
        audio_data = f.read()

    # Skip WAV header (first 44 bytes)
    audio_data = audio_data[44:]

    # Collect transcript
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
                # Interim transcript
                print(f"\r  Interim: {text}", end="", flush=True)

            elif event == "EndOfTurn" and text:
                # Final transcript
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

    # Step 2: LLM - Get response
    print("🤖 Step 2: Getting LLM response from OpenAI...\n")

    # Create conversation
    conversation_id = await llm.create_conversation()
    print(f"  ✓ Created conversation: {conversation_id}\n")

    # Stream LLM response
    print(f"  User: {transcript}")
    print("  Assistant: ", end="", flush=True)

    llm_response = ""
    async for chunk in llm.stream_complete(
        input=transcript,
        conversation_id=conversation_id,
    ):
        print(chunk, end="", flush=True)
        llm_response += chunk

    print("\n")

    if not llm_response:
        print("✗ No LLM response received")
        return

    # Step 3: TTS - Synthesize response to audio
    print("🔊 Step 3: Synthesizing response with Deepgram TTS...\n")

    output_dir = Path(__file__).parent / "data"
    output_file = output_dir / "pipeline_output.wav"

    audio_path = await tts.synthesize(
        text=llm_response,
        output_file=output_file,
        model="aura-2-thalia-en",
        encoding="linear16",
        sample_rate=16000,
    )

    print(f"  ✓ Audio synthesized to {audio_path.name}")
    print(f"  File size: {audio_path.stat().st_size} bytes\n")

    # Summary
    print("=" * 50)
    print("✓ Pipeline complete!")
    print(f"  Input:  {audio_file.name}")
    print(f"  Output: {output_file.name}")
    print(f"  Transcript: {transcript}")
    print(f"  Response: {llm_response[:100]}..." if len(llm_response) > 100 else f"  Response: {llm_response}")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())
