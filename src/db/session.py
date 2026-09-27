import os
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine


_engine: Optional[AsyncEngine] = None
_sessionmaker: Optional[async_sessionmaker[AsyncSession]] = None


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"{name} is not set")
    return value


def _build_async_database_url() -> str:
    """
    Production-friendly:
    - Prefer DATABASE_URL if user provides it.
    - Otherwise build from DB_* variables.

    For SQLAlchemy async + asyncpg, URL should be:
    postgresql+asyncpg://user:pass@host:port/dbname
    """
    direct = os.getenv("DATABASE_URL")
    if direct:
        # If someone provides a sync URL (postgresql://...), SQLAlchemy async won't accept it.
        # We keep it strict to avoid surprising runtime errors.
        if "postgresql+asyncpg://" in direct:
            return direct
        raise RuntimeError(
            "DATABASE_URL must use async driver. Example: "
            "postgresql+asyncpg://user:pass@postgres:5432/dbname"
        )

    host = os.getenv("DB_HOST", "postgres")
    port = os.getenv("DB_PORT", "5432")
    name = _require_env("DB_NAME")
    user = _require_env("DB_USER")
    password = _require_env("DB_PASSWORD")

    return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{name}"


async def init_engine() -> AsyncEngine:
    global _engine, _sessionmaker
    if _engine is not None and _sessionmaker is not None:
        return _engine

    _engine = create_async_engine(
        _build_async_database_url(),
        pool_pre_ping=True,
        future=True,
    )
    _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    if _sessionmaker is None:
        raise RuntimeError("DB engine is not initialized. Call init_engine() on startup.")
    return _sessionmaker


async def dispose_engine() -> None:
    global _engine, _sessionmaker
    if _engine is None:
        return
    await _engine.dispose()
    _engine = None
    _sessionmaker = None

