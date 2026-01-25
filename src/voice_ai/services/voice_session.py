"""
Voice session orchestrator.

Manages the full STT → LLM → TTS pipeline for a single voice conversation.
Format-agnostic: expects PCM 16kHz mono in/out, endpoints handle conversion.
"""

import asyncio
import logging
import time
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

    Usage:
        async with VoiceSession(websocket) as session:
            # STT connection automatically opened
            await session.handle_audio_chunk(audio_data)
            # ... STT connection automatically closed on exit
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

        # Interrupt handling
        self._speak_epoch = 0  # Incremented to invalidate old audio
        self._turn_task: asyncio.Task | None = None

        self._last_interrupt_monotonic: float = 0.0
        self._barge_in_latched: bool = False
        self._interrupt_debounce_s: float = 0.400
        self._update_interrupt_min_chars: int = 4
        
        self._tts_task: asyncio.Task | None = None  # NEW: cancellable TTS runner task

        logger.info("VoiceSession initialized")

    async def __aenter__(self):
        """
        Enter async context manager - opens persistent STT connection.

        Consistent with Deepgram SDK pattern (async with).
        """
        logger.info("📞 Voice session starting")

        # Open persistent STT connection (stays open for entire call)
        # Matches Deepgram SDK examples pattern
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

        # Register ASYNC event handlers (like Deepgram SDK examples!)
        async def on_stt_message(message):
            msg_type = getattr(message, "type", "Unknown")

            if msg_type == "TurnInfo":
                event = getattr(message, "event", "")
                text = getattr(message, "transcript", "") or ""

                if event == "StartOfTurn":
                    logger.info(f"🎤 STT StartOfTurn detected (state={self.state})")

                    if self.state == "speaking":
                        now = time.monotonic()
                        if not self._barge_in_latched and (now - self._last_interrupt_monotonic) >= self._interrupt_debounce_s:
                            self._barge_in_latched = True
                            self._last_interrupt_monotonic = now
                            asyncio.create_task(self._handle_interrupt(reason="StartOfTurn"))

                elif event == "Update" and text:
                    if self.state == "speaking":
                        cleaned = text.strip()
                        if len(cleaned) >= self._update_interrupt_min_chars:
                            now = time.monotonic()
                            if not self._barge_in_latched and (now - self._last_interrupt_monotonic) >= self._interrupt_debounce_s:
                                self._barge_in_latched = True
                                self._last_interrupt_monotonic = now
                                asyncio.create_task(self._handle_interrupt(reason=f"Update:{cleaned[:20]}"))

                    logger.debug(f"Interim (state={self.state}): '{text}'")

                elif event == "EndOfTurn" and text:
                    self._barge_in_latched = False  # reset latch for next time
                    logger.info(f"✓ STT final (state={self.state}): '{text}'")
                    asyncio.create_task(self.on_turn_end(text))

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

        # NOTE: Keepalive for v2 Flux is broken in SDK 5.3.1
        # Connection will timeout after ~20-30s of silence
        # See: https://github.com/deepgram/deepgram-python-sdk/issues/[YOUR_ISSUE_NUMBER]
        # Workaround: Keep calls under 30s or implement reconnection (future work)

        self.state = "listening"
        logger.info("🎤 Ready - listening for audio")

        return self


    async def send_audio(self, pcm_data: bytes) -> None:
        """
        Send audio to client (PCM format).

        Subclasses must override this to handle transport-specific formatting.
        (e.g., Twilio converts PCM → μ-law and wraps in JSON)

        Args:
            pcm_data: PCM linear16 16kHz mono audio bytes
        """
        raise NotImplementedError("Subclass must implement send_audio()")

    async def clear_audio_buffer(self) -> None:
        """
        Clear audio playback buffer (interrupt handling).

        Subclasses should override this to flush transport-specific buffers.
        (e.g., Twilio's "clear" event, browser AudioContext buffer clear)

        Default implementation does nothing (no buffer to clear).
        """
        pass  # Default: no-op

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

    async def _handle_interrupt(self, reason: str = "") -> None:
        """
        Handle user interruption during AI speech.

        Called when user starts speaking while AI is talking (barge-in).
        Stops current audio playback immediately.
        """
        if self.state != "speaking":
            return  # already handled

        logger.info(f"🛑 Handling interrupt ({reason}) - stopping AI speech")

        # Increment epoch to invalidate any in-flight audio chunks
        self._speak_epoch += 1
        logger.debug(f"Epoch incremented to {self._speak_epoch}")

        # Clear Twilio's audio playback buffer
        await self.clear_audio_buffer()

        # Cancel TTS runner if active
        if self._tts_task and not self._tts_task.done():
            self._tts_task.cancel()
            try:
                await self._tts_task
            except asyncio.CancelledError:
                pass

        # Reset state to listening (user will finish speaking, then on_turn_end will be called)
        self.state = "listening"
        logger.info("✓ Interrupt handled - ready for user input")

    async def on_turn_end(self, transcript: str) -> None:
        """
        Handle end of user's turn.

        Triggers LLM + TTS pipeline.

        Args:
            transcript: Final transcript from STT
        """
        logger.info(f"🎙️  on_turn_end() called - state: {self.state}, transcript: '{transcript}'")

        # Cancel any previous turn still running
        if self._turn_task and not self._turn_task.done():
            logger.warning("Previous turn still active, cancelling it")
            self._turn_task.cancel()
            try:
                await self._turn_task
            except asyncio.CancelledError:
                pass

        # Start new turn (non-blocking task)
        self._turn_task = asyncio.create_task(self._run_turn(transcript))

    async def _run_turn(self, transcript: str) -> None:
        """
        Run a complete turn: process input and generate response.

        Handles cancellation gracefully to ensure state is reset.

        Args:
            transcript: User's transcribed speech
        """
        try:
            self.state = "processing"
            logger.info("→ Processing turn...")

            # Process with LLM and synthesize response
            await self.process_llm_and_tts(transcript)

        except asyncio.CancelledError:
            logger.info("Turn cancelled (interrupted)")
            raise

        finally:
            # Always reset to listening state
            self.state = "listening"
            logger.info("✓ Turn complete - back to listening\n")

    async def process_llm_and_tts(self, user_input: str) -> None:
        """
        Process user input through LLM and synthesize audio response.

        Uses sentence-by-sentence streaming for optimal quality + low latency:
        - Buffer LLM chunks until sentence boundary (. ! ? \n)
        - Send complete sentences to TTS for natural synthesis
        - Audio starts playing after first sentence (still fast!)
        - Much better quality than raw token streaming

        Args:
            user_input: User's transcribed speech
        """
        # Create conversation on first turn
        if not self.conversation_id:
            self.conversation_id = await self.llm.create_conversation()
            logger.info(f"✓ Conversation created: {self.conversation_id}")

        logger.info(f"→ LLM input: '{user_input}'")

        # State transition: processing → speaking
        # Increment epoch to invalidate any previous audio chunks
        self._speak_epoch += 1
        logger.info(f"🔄 State change: {self.state} → speaking (epoch={self._speak_epoch})")
        self.state = "speaking"
        
        # New: Reset latch for new turn
        self._barge_in_latched = False

        async def tts_runner():
            # Open persistent TTS connection (async!)
            async with self.tts.client.speak.v1.connect(
                model="aura-2-thalia-en",
                encoding="linear16",
                sample_rate=16000,
            ) as tts_connection:
                # Register async audio handler
                audio_chunk_count = 0
                dropped_chunk_count = 0

                # Capture current epoch - audio from this TTS session is only valid for this epoch
                current_epoch = self._speak_epoch

                async def on_tts_audio(message):
                    nonlocal audio_chunk_count, dropped_chunk_count

                    if isinstance(message, bytes):
                        audio_chunk_count += 1

                        # Check if this audio is still valid (not interrupted)
                        if current_epoch != self._speak_epoch:
                            dropped_chunk_count += 1
                            if dropped_chunk_count == 1:
                                logger.info(f"🗑️  Dropping stale audio (epoch {current_epoch} != {self._speak_epoch})")
                            return  # Drop stale audio on the floor

                        # Log first chunk only
                        if audio_chunk_count == 1:
                            logger.info(f"🔊 TTS audio received: {len(message)} bytes (first chunk)")
                        # Send PCM audio to client
                        await self.send_audio(message)
                    else:
                        # Non-audio message (metadata, warnings, etc.)
                        logger.debug(f"TTS message: {type(message).__name__}")

                async def on_tts_error(error):
                    logger.error(f"❌ TTS error: {error}")

                async def on_tts_close(close_msg):
                    logger.warning(f"⚠️  TTS connection closed: {close_msg}")

                tts_connection.on(EventType.MESSAGE, on_tts_audio)
                tts_connection.on(EventType.ERROR, on_tts_error)
                tts_connection.on(EventType.CLOSE, on_tts_close)

                # Start TTS listening task (async, not thread!)
                listen_task = asyncio.create_task(tts_connection.start_listening())

                try:
                    # Stream LLM and synthesize sentence-by-sentence
                    from deepgram.speak.v1.types import SpeakV1Flush, SpeakV1Text
                    import re

                    chunk_count = 0
                    sentence_count = 0
                    sentence_buffer = ""

                    async def send_to_tts(text: str):
                        """Send text to TTS and flush."""
                        nonlocal sentence_count
                        if not text.strip():
                            return

                        sentence_count += 1
                        # Strip markdown formatting (TTS doesn't handle it well)
                        clean_text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)  # **bold** → bold
                        clean_text = re.sub(r'\*(.+?)\*', r'\1', clean_text)  # *italic* → italic
                        clean_text = clean_text.strip()

                        logger.info(f"→ TTS sentence {sentence_count}: '{clean_text[:80]}{'...' if len(clean_text) > 80 else ''}'")

                        await tts_connection.send_text(SpeakV1Text(text=clean_text))
                        await tts_connection.send_flush(SpeakV1Flush(type="Flush"))

                    async for llm_chunk in self.llm.stream_complete(
                        input=user_input,
                        conversation_id=self.conversation_id,
                    ):
                        chunk_count += 1
                        sentence_buffer += llm_chunk

                        # Log first few chunks for debugging
                        if chunk_count <= 5:
                            logger.debug(f"LLM chunk {chunk_count}: '{llm_chunk}'")

                        # Check for sentence boundaries (. ! ? or newline)
                        # Split on these and send complete sentences immediately
                        while True:
                            # Find the first sentence ending
                            match = re.search(r'[.!?]\s+|\n\n+', sentence_buffer)
                            if not match:
                                break  # No complete sentence yet

                            # Extract sentence and send to TTS
                            end_pos = match.end()
                            sentence = sentence_buffer[:end_pos]
                            sentence_buffer = sentence_buffer[end_pos:]

                            await send_to_tts(sentence)

                    # Send any remaining text in buffer (if last response didn't end with punctuation)
                    if sentence_buffer.strip():
                        await send_to_tts(sentence_buffer)

                    logger.info(f"← LLM: {chunk_count} chunks → {sentence_count} sentences")

                    # Send Close message (signals end of input to TTS)
                    # TTS will finish generating audio for all sent text, then close connection
                    from deepgram.speak.v1.types import SpeakV1Close

                    await tts_connection.send_close(SpeakV1Close(type="Close"))
                    logger.debug("Sent Close message to TTS, waiting for audio generation to complete...")

                    # Await listen_task - it will complete when TTS finishes processing all audio
                    await listen_task
                    logger.debug("TTS listen task completed successfully")

                except asyncio.CancelledError:
                    logger.warning("TTS runner cancelled")
                    # Make sure listen_task is cancelled on interrupt
                    if not listen_task.done():
                        listen_task.cancel()
                    raise

                except Exception as e:
                    # Catch SDK validation errors or other exceptions
                    logger.error(f"TTS runner failed: {type(e).__name__}: {e}")
                    # Don't re-raise - TTS already sent audio, just log the cleanup error
                    if not listen_task.done():
                        listen_task.cancel()
                
                logger.info(f"🔊 TTS audio: {audio_chunk_count} total chunks received")

        # Assign task so it can be cancelled
        self._tts_task = asyncio.create_task(tts_runner())
        try:
            await self._tts_task
        finally:
            self._tts_task = None

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """
        Exit async context manager - closes persistent STT connection.

        Ensures proper cleanup even if exceptions occur during session.
        Consistent with Deepgram SDK pattern (async with).
        """
        logger.info("Cleaning up voice session")

        # Close STT connection properly (matches Deepgram SDK examples!)
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
                    await self._stt_context_manager.__aexit__(exc_type, exc_val, exc_tb)
            except Exception as e:
                logger.error(f"Error closing STT connection: {e}")

        logger.info("Voice session cleaned up")
        return False  # Don't suppress exceptions
