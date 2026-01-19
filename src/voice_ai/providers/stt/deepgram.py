"""
Deepgram STT using Flux model.

Direct SDK usage - no abstractions.
"""

import threading

from deepgram import DeepgramClient
from deepgram.core.events import EventType

from voice_ai.config import settings


class DeepgramSTT:
    """
    Deepgram Flux STT provider.

    Simple wrapper around Deepgram SDK for streaming transcription.
    """

    def __init__(self, api_key: str | None = None):
        """Initialize with API key from settings or parameter."""
        self.api_key = api_key or settings.deepgram_api_key
        self.client = DeepgramClient(api_key=self.api_key)
        self.connection = None
        self.connection_manager = None
        self.listener_thread = None

    def connect(
        self,
        on_message,
        model: str = "flux-general-en",
        encoding: str = "linear16",
        sample_rate: int = 16000,
    ):
        """
        Open connection to Deepgram Flux.

        Args:
            on_message: Callback for messages (receives raw Deepgram response)
            model: Deepgram model (flux-general-en for turn detection)
            encoding: Audio encoding (linear16 = PCM)
            sample_rate: Sample rate in Hz

        Returns:
            Connection object (context manager)
        """
        self.connection_manager = self.client.listen.v2.connect(
            model=model,
            encoding=encoding,
            sample_rate=sample_rate,
        )

        # Enter context manager to get actual connection
        self.connection = self.connection_manager.__enter__()
        self.connection.on(EventType.MESSAGE, on_message)

        # Start listening in background thread
        self.listener_thread = threading.Thread(
            target=self.connection.start_listening,
            daemon=True,
        )
        self.listener_thread.start()

        return self.connection

    def send_audio(self, audio_chunk: bytes):
        """Send audio chunk to Deepgram."""
        if self.connection:
            self.connection.send_media(audio_chunk)

    def close(self):
        """Close the connection."""
        if self.connection_manager:
            self.connection_manager.__exit__(None, None, None)
            self.connection = None
            self.connection_manager = None
