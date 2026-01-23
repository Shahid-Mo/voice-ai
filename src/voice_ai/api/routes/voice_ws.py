"""
WebSocket endpoints for voice AI.

Handles bidirectional audio streaming for:
- Twilio Media Streams (phone calls)
- Browser WebSocket (future)
"""

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

    # Create voice session
    session = TwilioVoiceSession(websocket)

    try:
        async for message in websocket.iter_text():
            data = json.loads(message)
            event_type = data.get("event")

            if event_type == "start":
                # Call started
                stream_sid = data.get("start", {}).get("streamSid")
                logger.info(f"Stream started: {stream_sid}")
                await session.on_start(data)

                # Start the voice session (opens persistent STT connection)
                await session.start()

            elif event_type == "media":
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
                await session.cleanup()
                break

    except WebSocketDisconnect:
        logger.info("Twilio disconnected")
        await session.cleanup()
    except Exception as e:
        logger.error(f"Error in Twilio WebSocket: {e}", exc_info=True)
        await session.cleanup()
        raise


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

    async def send_json(self, data: dict) -> None:
        """
        Send JSON message to client.

        For Twilio, we could send marks (metadata) but generally
        we just send audio. This override prevents raw JSON from
        being sent to Twilio which expects specific message formats.

        Args:
            data: Message data (type, content, etc.)
        """
        # Twilio doesn't support arbitrary JSON messages
        # We could send "mark" events for tracking, but for now skip
        # Only audio is sent via send_audio()
        pass
