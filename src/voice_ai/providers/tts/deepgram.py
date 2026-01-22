"""
Deepgram TTS using Aura 2 model.

Async implementation following official Deepgram SDK patterns.
"""

import asyncio
import threading
import wave
from collections.abc import Callable
from pathlib import Path
from typing import Any

from deepgram import DeepgramClient
from deepgram.core.events import EventType
from deepgram.speak.v1.types import (
    SpeakV1Close,
    SpeakV1Flush,
    SpeakV1Text,
)

from voice_ai.config import settings


class DeepgramTTS:
    """
    Deepgram Aura 2 TTS provider.

    Async wrapper around Deepgram SDK for streaming text-to-speech.
    """

    def __init__(self, api_key: str | None = None):
        """
        Initialize with API key from settings or parameter.

        Args:
            api_key: Deepgram API key (defaults to settings.deepgram_api_key)
        """
        self.api_key = api_key or settings.deepgram_api_key
        self.client = DeepgramClient(api_key=self.api_key)

    async def synthesize_stream(
        self,
        text: str,
        on_audio: Callable[[bytes], None],
        on_complete: Callable[[], None] | None = None,
        model: str = "aura-2-thalia-en",
        encoding: str = "linear16",
        sample_rate: int = 16000,
    ) -> None:
        """
        Stream text to Deepgram and get audio via callback.

        Args:
            text: Text to synthesize
            on_audio: Callback for each audio chunk (binary data)
            on_complete: Optional callback when synthesis completes
            model: Deepgram Aura model (aura-2-thalia-en, aura-2-arcas-en, etc)
            encoding: Audio encoding (linear16 = PCM)
            sample_rate: Sample rate in Hz

        Example:
            def on_audio(chunk: bytes):
                # Write to file or stream to speaker
                with open("output.wav", "ab") as f:
                    f.write(chunk)

            await tts.synthesize_stream("Hello world!", on_audio)
        """
        # Track completion
        done_event = asyncio.Event()

        # Connect using sync context manager (Deepgram SDK is sync, not async)
        with self.client.speak.v1.connect(
            model=model,
            encoding=encoding,
            sample_rate=sample_rate,
        ) as connection:

            def on_message(message: Any) -> None:
                """Handle messages from Deepgram."""
                if isinstance(message, bytes):
                    # Binary audio data
                    on_audio(message)
                else:
                    # Text event (Connected, Flushed, Close, etc)
                    msg_type = getattr(message, "type", "Unknown")
                    if msg_type == "Close":
                        # Signal completion
                        asyncio.run_coroutine_threadsafe(
                            done_event.set(), asyncio.get_event_loop()
                        )

            # Register event handlers
            connection.on(EventType.MESSAGE, on_message)

            # Start listening in background thread (not async)
            threading.Thread(target=connection.start_listening, daemon=True).start()

            # Send text for synthesis
            connection.send_text(SpeakV1Text(text=text))

            # Flush to ensure all audio is sent
            connection.send_flush(SpeakV1Flush(type="Flush"))

            # Wait for completion or timeout
            try:
                await asyncio.wait_for(done_event.wait(), timeout=30.0)
            except TimeoutError:
                pass

            # Close connection
            connection.send_close(SpeakV1Close(type="Close"))

            # Brief wait for close to process
            await asyncio.sleep(0.1)

            # Call completion callback
            if on_complete:
                on_complete()

    async def synthesize(
        self,
        text: str,
        output_file: str | Path,
        model: str = "aura-2-thalia-en",
        encoding: str = "linear16",
        sample_rate: int = 16000,
    ) -> Path:
        """
        Synthesize text to audio file.

        Args:
            text: Text to synthesize
            output_file: Path to write audio file (WAV format)
            model: Deepgram Aura model
            encoding: Audio encoding (linear16 = PCM)
            sample_rate: Sample rate in Hz

        Returns:
            Path to the generated audio file

        Example:
            audio_path = await tts.synthesize("Hello!", "output.wav")
        """
        output_path = Path(output_file)

        # Generate WAV header (Deepgram returns raw audio without container)
        with wave.open(str(output_path), "wb") as wav_file:
            wav_file.setnchannels(1)  # Mono
            wav_file.setsampwidth(2)  # 16-bit
            wav_file.setframerate(sample_rate)

        # Append audio chunks to file
        def on_audio(chunk: bytes) -> None:
            with open(output_path, "ab") as f:
                f.write(chunk)

        # Stream synthesis
        await self.synthesize_stream(
            text=text,
            on_audio=on_audio,
            model=model,
            encoding=encoding,
            sample_rate=sample_rate,
        )

        return output_path
