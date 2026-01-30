"""Database connection and session management."""
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

# Use async PostgreSQL driver
DATABASE_URL = os.getenv(
    "DATABASE_URL", 
    "postgresql+asyncpg://lotus:lotus@localhost:5432/blacklotus"
)

engine = create_async_engine(
    DATABASE_URL,
    echo=False,  # Set True for SQL logging
    future=True
)

async_session = sessionmaker(
    engine, 
    class_=AsyncSession, 
    expire_on_commit=False
)


async def init_db():
    """Create tables on startup."""
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)


async def close_db():
    """Close connections on shutdown."""
    await engine.dispose()


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for FastAPI routes."""
    async with async_session() as session:
        yield session
