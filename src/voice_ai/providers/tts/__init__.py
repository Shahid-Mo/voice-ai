"""Text-to-Speech providers."""

from voice_ai.providers.tts.base import TTSProvider, TTSResult
from voice_ai.providers.tts.deepgram import DeepgramTTS

__all__ = ["TTSProvider", "TTSResult", "DeepgramTTS"]
