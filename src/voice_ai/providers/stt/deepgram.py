"""
Deepgram STT using Flux model.

Fully async implementation using AsyncDeepgramClient.
"""

import asyncio
from collections.abc import Callable
from typing import Any

from deepgram import AsyncDeepgramClient
from deepgram.core.events import EventType
from deepgram.listen.v2.types import ListenV2CloseStream

from voice_ai.config import settings


class DeepgramSTT:
    """
    Deepgram Flux STT provider.

    Fully async implementation using AsyncDeepgramClient - no threading needed.
    """

    def __init__(self, api_key: str | None = None):
        """
        Initialize with API key from settings or parameter.

        Args:
            api_key: Deepgram API key (defaults to settings.deepgram_api_key)
        """
        self.api_key = api_key or settings.deepgram_api_key
        self.client = AsyncDeepgramClient(api_key=self.api_key)

    async def transcribe_stream(
        self,
        audio_data: bytes,
        on_message: Callable[[Any], None],
        model: str = "flux-general-en",
        encoding: str = "linear16",
        sample_rate: int = 16000,
        chunk_size: int = 4096,
    ) -> None:
        """
        Stream audio to Deepgram and get transcripts via callback.

        Args:
            audio_data: Raw audio bytes (PCM data, no header)
            on_message: Callback for each message from Deepgram
            model: Deepgram model (flux-general-en for turn detection)
            encoding: Audio encoding (linear16 = PCM)
            sample_rate: Sample rate in Hz
            chunk_size: Bytes per chunk (4096 = ~128ms at 16kHz linear16)

        Example:
            def on_message(msg):
                if msg.type == "TurnInfo" and msg.event == "EndOfTurn":
                    print(msg.transcript)

            await stt.transcribe_stream(audio_data, on_message)
        """
        # Calculate chunk duration for real-time streaming
        # At 16kHz mono linear16: 16000 samples/sec * 2 bytes/sample = 32000 bytes/sec
        bytes_per_second = sample_rate * 2  # 2 bytes per sample for linear16
        chunk_duration = chunk_size / bytes_per_second

        # Connect using async context manager - NO THREADING!
        async with self.client.listen.v2.connect(
            model=model,
            encoding=encoding,
            sample_rate=sample_rate,
        ) as connection:
            # Register message handler
            connection.on(EventType.MESSAGE, on_message)

            # Start listening (async task, not thread!)
            listen_task = asyncio.create_task(connection.start_listening())

            # Send audio in chunks at real-time speed
            for i in range(0, len(audio_data), chunk_size):
                chunk = audio_data[i : i + chunk_size]
                await connection.send_media(chunk)

                # Sleep to simulate real-time streaming
                await asyncio.sleep(chunk_duration)

            # Wait briefly for final processing
            await asyncio.sleep(0.5)

            # Signal that we're done sending audio
            await connection.send_close_stream(ListenV2CloseStream(type="CloseStream"))

            # Wait for listening to complete
            await listen_task

            # Connection automatically closed when exiting async context manager
