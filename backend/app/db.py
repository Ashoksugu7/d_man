"""Async database setup for the garment service (Phase A).

PostgreSQL via asyncpg by default; override with DATABASE_URL. Tests/dev can
point DATABASE_URL at sqlite+aiosqlite:// to run without a Postgres server.
"""
from __future__ import annotations

import os
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncSession, async_sessionmaker, create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

# Default to the shared local Postgres; override via env in prod/dev/tests.
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/doctor_appointment",
)

# Garment tables live under a prefix so they don't collide with other apps that
# share this database.
TABLE_PREFIX = os.getenv("GARMENT_TABLE_PREFIX", "vton_")

engine = create_async_engine(DATABASE_URL, echo=False, pool_pre_ping=True, future=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


class Base(DeclarativeBase):
    pass


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: yields an async session."""
    async with SessionLocal() as session:
        yield session


async def create_all() -> None:
    """Create tables if missing (dev convenience; prod uses Alembic)."""
    from sqlalchemy import text
    from . import models  # noqa: F401 — ensure models are registered
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Best-effort add of columns introduced after a table already exists
        # (dev only; Postgres supports IF NOT EXISTS). Alembic handles prod.
        if conn.dialect.name == "postgresql":
            await conn.execute(text(
                f"ALTER TABLE {TABLE_PREFIX}garment "
                f"ADD COLUMN IF NOT EXISTS fit_params JSONB"
            ))
