"""
Voice session orchestrator.

Manages the full STT → LLM → TTS pipeline for a single voice conversation.
Format-agnostic: expects PCM 16kHz mono in/out, endpoints handle conversion.
"""

import asyncio
import base64
import logging
import re
from typing import Literal

from deepgram import AsyncDeepgramClient
from deepgram.core.events import EventType
from deepgram.listen.v2.types import ListenV2CloseStream
from fastapi import WebSocket

from voice_ai.config import settings
from voice_ai.providers.llm.openai import OpenAILLM
from voice_ai.providers.tts.deepgram import DeepgramTTS

logger = logging.getLogger(__name__)

State = Literal["idle", "listening", "processing", "speaking"]


class VoiceSession:
    """
    Orchestrates voice AI pipeline for a single conversation.

    Format-agnostic orchestrator that handles:
    - STT (speech → text) with turn detection via continuous streaming
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

        # Initialize providers
        self.stt_client = AsyncDeepgramClient(api_key=settings.deepgram_api_key)
        self.llm = OpenAILLM()
        self.tts = DeepgramTTS()

        # STT connection (persistent, kept open for continuous streaming)
        self.stt_connection = None
        self.stt_listen_task = None
        self._stt_context_manager = None

        # Session state
        self.state: State = "idle"
        self.conversation_id: str | None = None

        logger.info("VoiceSession initialized")

    async def start(self):
        """Start the session - opens persistent STT connection."""
        logger.info("📞 Voice session started")

        # Open persistent STT connection (stays open for entire call)
        # Use async with context manager (YOUR working test pattern!)
        self._stt_context_manager = self.stt_client.listen.v2.connect(
            model="flux-general-en",
            encoding="linear16",
            sample_rate=16000,
            # End-of-turn detection optimization (simple mode)
            eot_threshold="0.6",  # Lower than default 0.7 for faster detection
            eot_timeout_ms="3000",  # 3 seconds instead of default 5 seconds
        )

        # Enter the context manager
        self.stt_connection = await self._stt_context_manager.__aenter__()
        logger.info("✓ STT connection opened")

        # Register ASYNC event handlers (like your test!)
        async def on_stt_message(message):
            msg_type = getattr(message, "type", "Unknown")

            if msg_type == "TurnInfo":
                event = getattr(message, "event", "")
                text = getattr(message, "transcript", "")

                if event == "Update" and text:
                    # Interim transcript
                    await self.send_transcript(text, is_final=False)

                elif event == "EndOfTurn" and text:
                    # Final transcript - user stopped talking
                    logger.info(f"✓ STT: '{text}'")
                    await self.send_transcript(text, is_final=True)
                    await self.on_turn_end(text)

            elif msg_type == "Connected":
                logger.info("✅ Connected to Deepgram Flux")

        async def on_stt_error(error):
            logger.error(f"❌ STT error: {error}")

        async def on_stt_close(close_msg):
            logger.warning(f"⚠️  STT connection closed: {close_msg}")

        self.stt_connection.on(EventType.MESSAGE, on_stt_message)
        self.stt_connection.on(EventType.ERROR, on_stt_error)
        self.stt_connection.on(EventType.CLOSE, on_stt_close)

        # Start listening task (runs continuously)
        self.stt_listen_task = asyncio.create_task(
            self.stt_connection.start_listening()
        )

        self.state = "listening"
        await self.send_status("Listening...")
        logger.info("🎤 Listening...")

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

        Sends directly to persistent STT connection for continuous streaming.

        Args:
            pcm_chunk: PCM linear16 16kHz mono audio bytes
        """
        if not self.stt_connection:
            logger.warning("Received audio but STT connection not ready - call start() first")
            return

        # Send directly to STT connection (continuous streaming!)
        # (No logging here - happens 50+ times/second!)
        await self.stt_connection.send_media(pcm_chunk)

    async def on_turn_end(self, transcript: str) -> None:
        """
        Handle end of user's turn.

        Triggers LLM + TTS pipeline.

        Args:
            transcript: Final transcript from STT
        """
        self.state = "processing"
        await self.send_status("Processing...")

        # Process with LLM and synthesize response
        await self.process_llm_and_tts(transcript)

        # Reset to listening (STT connection stays open!)
        self.state = "listening"
        await self.send_status("Listening...")
        logger.info("✓ Turn complete\n")

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
            logger.info(f"✓ Conversation created: {self.conversation_id}")

        logger.info(f"→ LLM: '{user_input}'")

        self.state = "speaking"
        await self.send_status("Speaking...")

        # Open persistent TTS connection (async!)
        async with self.tts.client.speak.v1.connect(
            model="aura-2-thalia-en",
            encoding="linear16",
            sample_rate=16000,
        ) as tts_connection:
            # Register async audio handler
            audio_chunk_count = 0

            async def on_tts_audio(message):
                nonlocal audio_chunk_count

                if isinstance(message, bytes):
                    audio_chunk_count += 1
                    # Log first chunk only
                    if audio_chunk_count == 1:
                        logger.info(f"🔊 TTS audio received: {len(message)} bytes (first chunk)")
                    # Send PCM audio to client
                    await self.send_audio(message)

            tts_connection.on(EventType.MESSAGE, on_tts_audio)

            # Start TTS listening task (async, not thread!)
            listen_task = asyncio.create_task(tts_connection.start_listening())

            # Stream LLM and synthesize sentence-by-sentence
            sentence_buffer = ""
            sentence_count = 0

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

                    sentence_count += 1

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

                sentence_count += 1

                await tts_connection.send_text(
                    SpeakV1Text(text=sentence_buffer.strip())
                )
                await tts_connection.send_flush(SpeakV1Flush(type="Flush"))

            logger.info(f"← TTS: {sentence_count} sentence(s) synthesized")
            logger.info(f"🔊 TTS audio: {audio_chunk_count} total chunks received")

            # Wait for final audio processing
            await asyncio.sleep(0.5)

            # Close TTS connection properly
            from deepgram.speak.v1.types import SpeakV1Close

            await tts_connection.send_close(SpeakV1Close(type="Close"))
            await listen_task

    async def cleanup(self) -> None:
        """Clean up resources when session ends."""
        logger.info("Cleaning up voice session")

        # Close STT connection properly (like your test!)
        if self.stt_connection:
            try:
                # Send close stream
                await self.stt_connection.send_close_stream(
                    ListenV2CloseStream(type="CloseStream")
                )
                # Wait for listen task
                if self.stt_listen_task:
                    await self.stt_listen_task
                # Exit context manager
                if self._stt_context_manager:
                    await self._stt_context_manager.__aexit__(None, None, None)
            except Exception as e:
                logger.error(f"Error closing STT connection: {e}")

        logger.info("Voice session cleaned up")
