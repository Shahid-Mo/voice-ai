"""
Voice session orchestrator.

Manages the full STT → LLM → TTS pipeline for a single voice conversation.
Format-agnostic: expects PCM 16kHz mono in/out, endpoints handle conversion.
"""

import asyncio
import base64
import re
from typing import Literal

from fastapi import WebSocket

from voice_ai.providers.llm.openai import OpenAILLM
from voice_ai.providers.stt.deepgram import DeepgramSTT
from voice_ai.providers.tts.deepgram import DeepgramTTS

State = Literal["idle", "listening", "processing", "speaking"]


class VoiceSession:
    """
    Orchestrates voice AI pipeline for a single conversation.

    Format-agnostic orchestrator that handles:
    - STT (speech → text) with turn detection
    - LLM (text → response) with streaming
    - TTS (response → speech) with sentence-by-sentence synthesis

    Expects PCM linear16 16kHz mono for all audio I/O.
    Endpoints handle format conversion (μ-law, WebM, etc. → PCM).
    """

    def __init__(self, websocket: WebSocket):
        """
        Initialize voice session for a WebSocket connection.

        Args:
            websocket: FastAPI WebSocket for bidirectional communication
        """
        self.websocket = websocket

        # Initialize providers (already async!)
        self.stt = DeepgramSTT()
        self.llm = OpenAILLM()
        self.tts = DeepgramTTS()

        # Session state
        self.state: State = "idle"
        self.conversation_id: str | None = None
        self.audio_buffer: list[bytes] = []

    async def send_json(self, data: dict) -> None:
        """Send JSON message to client."""
        await self.websocket.send_json(data)

    async def send_status(self, message: str) -> None:
        """Send status update to client."""
        await self.send_json({"type": "status", "message": message})

    async def send_transcript(self, text: str, is_final: bool = False) -> None:
        """Send transcript to client."""
        await self.send_json({
            "type": "transcript",
            "text": text,
            "is_final": is_final,
        })

    async def send_llm_text(self, text: str) -> None:
        """Send LLM response text to client (for display)."""
        await self.send_json({"type": "llm_text", "text": text})

    async def send_audio(self, pcm_data: bytes) -> None:
        """
        Send audio to client (PCM format).

        Note: Endpoint may convert PCM → transport format (μ-law, etc.)
        before actually sending over WebSocket.

        Args:
            pcm_data: PCM linear16 16kHz mono audio bytes
        """
        # Encode as base64 for JSON transport
        audio_base64 = base64.b64encode(pcm_data).decode()
        await self.send_json({"type": "audio", "data": audio_base64})

    async def handle_audio_chunk(self, pcm_chunk: bytes) -> None:
        """
        Handle incoming audio chunk (PCM format).

        Buffers audio and starts STT stream if needed.

        Args:
            pcm_chunk: PCM linear16 16kHz mono audio bytes
        """
        # Buffer audio
        self.audio_buffer.append(pcm_chunk)

        # Start listening if idle
        if self.state == "idle":
            await self.start_listening()

    async def start_listening(self) -> None:
        """Start STT streaming with buffered audio."""
        self.state = "listening"
        await self.send_status("Listening...")

        # Define STT event handler (async!)
        async def on_stt_message(message):
            msg_type = getattr(message, "type", "unknown")

            if msg_type == "TurnInfo":
                event = getattr(message, "event", "")
                text = getattr(message, "transcript", "")

                if event == "Update" and text:
                    # Interim transcript
                    await self.send_transcript(text, is_final=False)

                elif event == "EndOfTurn" and text:
                    # Final transcript - user stopped talking
                    await self.send_transcript(text, is_final=True)
                    await self.on_turn_end(text)

        # Stream buffered audio to STT
        audio_data = b"".join(self.audio_buffer)
        await self.stt.transcribe_stream(audio_data, on_stt_message)

    async def on_turn_end(self, transcript: str) -> None:
        """
        Handle end of user's turn.

        Triggers LLM + TTS pipeline.

        Args:
            transcript: Final transcript from STT
        """
        self.state = "processing"
        await self.send_status("Processing...")

        # Clear audio buffer
        self.audio_buffer = []

        # Process with LLM and synthesize response
        await self.process_llm_and_tts(transcript)

        # Reset to idle
        self.state = "idle"
        await self.send_status("Ready")

    async def process_llm_and_tts(self, user_input: str) -> None:
        """
        Process user input through LLM and synthesize audio response.

        Uses sentence-by-sentence streaming for low latency:
        - Buffer LLM tokens until sentence boundary
        - Immediately synthesize each sentence
        - First audio plays while LLM still generating

        Args:
            user_input: User's transcribed speech
        """
        # Create conversation on first turn
        if not self.conversation_id:
            self.conversation_id = await self.llm.create_conversation()

        self.state = "speaking"
        await self.send_status("Speaking...")

        # Open persistent TTS connection (async!)
        async with self.tts.client.speak.v1.connect(
            model="aura-2-thalia-en",
            encoding="linear16",
            sample_rate=16000,
        ) as tts_connection:
            from deepgram.core.events import EventType

            # Register async audio handler
            async def on_tts_audio(message):
                if isinstance(message, bytes):
                    # Send PCM audio to client
                    await self.send_audio(message)

            tts_connection.on(EventType.MESSAGE, on_tts_audio)

            # Start TTS listening task (async, not thread!)
            listen_task = asyncio.create_task(tts_connection.start_listening())

            # Stream LLM and synthesize sentence-by-sentence
            sentence_buffer = ""

            async for llm_chunk in self.llm.stream_complete(
                input=user_input,
                conversation_id=self.conversation_id,
            ):
                # Send LLM text to client for display
                await self.send_llm_text(llm_chunk)

                sentence_buffer += llm_chunk

                # Check for sentence boundary (. ! ?)
                if re.search(r"[.!?]\s*$", sentence_buffer):
                    from deepgram.speak.v1.types import SpeakV1Flush, SpeakV1Text

                    # Send sentence to TTS immediately
                    await tts_connection.send_text(
                        SpeakV1Text(text=sentence_buffer.strip())
                    )

                    # Flush to get audio NOW (don't wait for full response)
                    await tts_connection.send_flush(SpeakV1Flush(type="Flush"))

                    # Audio chunks will stream back while LLM continues
                    sentence_buffer = ""

            # Handle any remaining text
            if sentence_buffer.strip():
                from deepgram.speak.v1.types import SpeakV1Flush, SpeakV1Text

                await tts_connection.send_text(
                    SpeakV1Text(text=sentence_buffer.strip())
                )
                await tts_connection.send_flush(SpeakV1Flush(type="Flush"))

            # Wait for final audio processing
            await asyncio.sleep(0.5)

            # Close TTS connection properly
            from deepgram.speak.v1.types import SpeakV1Close

            await tts_connection.send_close(SpeakV1Close(type="Close"))
            await listen_task

    async def cleanup(self) -> None:
        """Clean up resources when session ends."""
        # Providers are connection-based, cleanup happens in context managers
        # Nothing to do here currently
        pass
