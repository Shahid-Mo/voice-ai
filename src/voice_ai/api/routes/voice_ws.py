"""
WebSocket endpoints for voice AI.

Handles bidirectional audio streaming for:
- Twilio Media Streams (phone calls)
- Browser WebSocket (future)
"""

import asyncio
import base64
import json
import logging

from fastapi import APIRouter, Request, Response, WebSocket, WebSocketDisconnect

from voice_ai.audio_utils import mulaw_to_pcm_16k, pcm_16k_to_mulaw
from voice_ai.services.voice_session import VoiceSession

logger = logging.getLogger(__name__)

router = APIRouter()


@router.api_route("/incoming-call", methods=["GET", "POST"])
async def incoming_call(request: Request):
    """
    Twilio webhook endpoint for incoming calls.

    When a call comes in, Twilio hits this endpoint. We respond with
    TwiML (XML) instructions telling Twilio to connect the call to our
    WebSocket stream.

    Returns:
        TwiML XML response with Stream instruction
    """
    # Get host header to build dynamic WebSocket URL
    host = request.headers.get("host")

    # Determine protocol (wss for production, ws for local dev)
    # Ngrok always uses HTTPS, so we use WSS
    protocol = "wss" if "ngrok" in host or "https" in str(request.url) else "ws"

    # TwiML: Connect call to our WebSocket endpoint
    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Connect>
        <Stream url="{protocol}://{host}/ws/twilio" />
    </Connect>
</Response>"""

    return Response(content=twiml, media_type="application/xml")


@router.websocket("/ws/twilio")
async def twilio_websocket(websocket: WebSocket):
    """
    Twilio Media Streams WebSocket endpoint.

    Handles bidirectional audio streaming for phone calls:
    - Receives: Twilio JSON messages with Base64-encoded mulaw 8kHz audio
    - Sends: Twilio JSON messages with Base64-encoded mulaw 8kHz audio

    Audio Flow:
    1. Twilio → JSON → Base64 decode → mulaw 8kHz
    2. Convert → PCM 16kHz
    3. VoiceSession processes (STT → LLM → TTS)
    4. PCM 16kHz → mulaw 8kHz
    5. Base64 encode → JSON → Twilio

    Protocol Reference:
    https://www.twilio.com/docs/voice/twiml/stream
    """
    await websocket.accept()
    logger.info("Twilio call connected")

    # Wait for "start" event before creating session
    start_data = None
    try:
        async for message in websocket.iter_text():
            data = json.loads(message)
            if data.get("event") == "start":
                start_data = data
                stream_sid = data.get("start", {}).get("streamSid")
                logger.info(f"Stream started: {stream_sid}")
                break
    except WebSocketDisconnect:
        logger.info("Twilio disconnected before stream started")
        return

    # Now enter session context (STT connection auto-opened)
    try:
        async with TwilioVoiceSession(websocket) as session:
            await session.on_start(start_data)

            # Process remaining events (media, stop)
            async for message in websocket.iter_text():
                data = json.loads(message)
                event_type = data.get("event")

                if event_type == "media":
                    # Audio chunk received (happens 50+ times/second - no logging!)
                    # Extract Base64-encoded mulaw payload
                    payload_b64 = data["media"]["payload"]

                    # Decode to mulaw bytes
                    mulaw_audio = base64.b64decode(payload_b64)

                    # Convert mulaw 8kHz → PCM 16kHz
                    pcm_audio = mulaw_to_pcm_16k(mulaw_audio, input_rate=8000)

                    # Feed to VoiceSession
                    await session.handle_audio_chunk(pcm_audio)

                elif event_type == "stop":
                    # Call ended
                    logger.info("Stream stopped")
                    break

    except WebSocketDisconnect:
        logger.info("Twilio disconnected")
    except Exception as e:
        logger.error(f"Error in Twilio WebSocket: {e}", exc_info=True)
        raise
    # Session automatically cleaned up on exit (async with)


class TwilioVoiceSession(VoiceSession):
    """
    Twilio-specific voice session wrapper.

    Extends VoiceSession to handle Twilio's message format:
    - Wraps outgoing audio in Twilio JSON format
    - Converts PCM 16kHz ↔ mulaw 8kHz
    """

    async def on_start(self, start_data: dict):
        """Handle Twilio stream start event."""
        # Extract stream metadata
        self.stream_sid = start_data.get("start", {}).get("streamSid")
        logger.info(f"📞 Stream SID: {self.stream_sid}")

        # Send welcome greeting
        await self._send_greeting()

    async def _send_greeting(self) -> None:
        """Send welcome greeting via TTS."""
        from deepgram.core.events import EventType
        from deepgram.speak.v1.types import SpeakV1Close, SpeakV1Flush, SpeakV1Text

        greeting = "Welcome to Hotel Continental. My name is Alex, i am your virtual . How may I help you today!?"
        logger.info(f"🎙️  Sending greeting: '{greeting}'")

        # Open TTS connection
        async with self.tts.client.speak.v1.connect(
            model="aura-2-thalia-en",
            encoding="linear16",
            sample_rate=16000,
        ) as tts_connection:
            # Register audio handler
            async def on_tts_audio(message):
                if isinstance(message, bytes):
                    await self.send_audio(message)

            tts_connection.on(EventType.MESSAGE, on_tts_audio)

            # Start listening task
            listen_task = asyncio.create_task(tts_connection.start_listening())

            try:
                # Send greeting text
                await tts_connection.send_text(SpeakV1Text(text=greeting))
                await tts_connection.send_flush(SpeakV1Flush(type="Flush"))

                # Close connection
                await tts_connection.send_close(SpeakV1Close(type="Close"))

                # Wait for audio to finish
                await listen_task
                logger.info("✓ Greeting sent")

            except Exception as e:
                logger.error(f"Error sending greeting: {e}", exc_info=True)
                if not listen_task.done():
                    listen_task.cancel()

    async def clear_audio_buffer(self) -> None:
        """
        Clear Twilio's audio playback buffer.

        Sends a "clear" event to immediately stop playing queued audio.
        Used for interrupt handling - stops old audio when user speaks.
        """
        clear_message = {
            "event": "clear",
            "streamSid": self.stream_sid,
        }

        await self.websocket.send_text(json.dumps(clear_message))
        logger.info("🧹 Cleared Twilio audio buffer (interrupt)")

    async def send_audio(self, pcm_data: bytes) -> None:
        """
        Send audio to Twilio.

        Overrides parent to wrap audio in Twilio's JSON format.

        Args:
            pcm_data: PCM linear16 16kHz mono (from TTS)
        """
        # Track audio chunks sent
        if not hasattr(self, "_audio_chunk_count"):
            self._audio_chunk_count = 0
        self._audio_chunk_count += 1

        # Convert PCM 16kHz → mulaw 8kHz
        mulaw_audio = pcm_16k_to_mulaw(pcm_data, output_rate=8000)

        # Base64 encode
        payload_b64 = base64.b64encode(mulaw_audio).decode("utf-8")

        # Log first chunk and summary every 10 chunks
        if self._audio_chunk_count == 1:
            logger.info(f"🔊 Sending audio to Twilio: PCM {len(pcm_data)} bytes → μ-law {len(mulaw_audio)} bytes → b64 {len(payload_b64)} chars")
        elif self._audio_chunk_count % 10 == 0:
            logger.info(f"🔊 Sent {self._audio_chunk_count} audio chunks to Twilio...")

        # Wrap in Twilio media message
        media_message = {
            "event": "media",
            "streamSid": self.stream_sid,
            "media": {"payload": payload_b64},
        }

        # Send as JSON
        await self.websocket.send_text(json.dumps(media_message))
