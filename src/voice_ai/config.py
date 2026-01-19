"""Application configuration using pydantic-settings."""

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Provider Selection
    stt_provider: Literal["deepgram"] = "deepgram"
    llm_provider: Literal["openai"] = "openai"
    tts_provider: Literal["deepgram"] = "deepgram"

    # Deepgram
    deepgram_api_key: str = ""

    # OpenAI
    openai_api_key: str = ""

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False


# Global settings instance
settings = Settings()
