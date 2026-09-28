"""Sync SQLAlchemy engine for RQ workers (no asyncio)."""
from __future__ import annotations

import os
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"{name} is not set")
    return value


def _build_sync_database_url() -> str:
    direct = os.getenv("DATABASE_URL_SYNC") or os.getenv("DATABASE_URL")
    if direct:
        if "postgresql+asyncpg://" in direct:
            return direct.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)
        if direct.startswith("postgresql://"):
            return direct.replace("postgresql://", "postgresql+psycopg://", 1)
        if "postgresql+psycopg://" in direct:
            return direct
        raise RuntimeError("DATABASE_URL_SYNC must be a sync Postgres URL")

    host = os.getenv("DB_HOST", "postgres")
    port = os.getenv("DB_PORT", "5432")
    name = _require_env("DB_NAME")
    user = _require_env("DB_USER")
    password = _require_env("DB_PASSWORD")
    return f"postgresql+psycopg://{user}:{password}@{host}:{port}/{name}"


@lru_cache(maxsize=1)
def get_sync_engine():
    return create_engine(_build_sync_database_url(), pool_pre_ping=True, future=True)


@lru_cache(maxsize=1)
def get_sync_sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(bind=get_sync_engine(), expire_on_commit=False, future=True)
