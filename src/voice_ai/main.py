"""FastAPI application entry point."""

from fastapi import FastAPI

from voice_ai.api.routes import health, voice_ws
from voice_ai.config import settings

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
