"""FastAPI application entry point."""

import logging

from fastapi import FastAPI

from voice_ai.api.routes import health, voice_ws
from voice_ai.config import settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,  # Use INFO - DEBUG is too noisy for audio streams
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# Reduce noise from external libraries
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

app = FastAPI(
    title="Voice AI",
    description="Modular Voice AI system with pluggable providers",
    version="0.1.0",
)

# Include routers
app.include_router(health.router)
app.include_router(voice_ws.router)


@app.get("/")
async def root() -> dict[str, str]:
    """Root endpoint."""
    return {
        "service": "voice-ai",
        "version": "0.1.0",
        "stt_provider": settings.stt_provider,
        "llm_provider": settings.llm_provider,
        "tts_provider": settings.tts_provider,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "voice_ai.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )
