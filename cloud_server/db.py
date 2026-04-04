from __future__ import annotations

import os
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

try:
    from cloud_server.data_models import Base
except ModuleNotFoundError as e:
    if e.name != "cloud_server":
        raise
    from data_models import Base


def _normalize_dsn(raw: str) -> str:
    dsn = (raw or "").strip()
    if not dsn:
        dsn = "sqlite+aiosqlite:///./project_claw_local.db"
    if dsn.startswith("postgresql://"):
        return dsn.replace("postgresql://", "postgresql+asyncpg://", 1)
    return dsn


DATABASE_URL = _normalize_dsn(os.getenv("DATABASE_URL", ""))
DB_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "20"))
DB_MAX_OVERFLOW = int(os.getenv("DB_MAX_OVERFLOW", "20"))
DB_POOL_TIMEOUT = int(os.getenv("DB_POOL_TIMEOUT", "30"))
DB_ECHO = os.getenv("DB_ECHO", "0") == "1"

if DATABASE_URL.startswith("sqlite+"):
    engine: AsyncEngine = create_async_engine(
        DATABASE_URL,
        echo=DB_ECHO,
    )
else:
    engine: AsyncEngine = create_async_engine(
        DATABASE_URL,
        echo=DB_ECHO,
        pool_pre_ping=True,
        pool_size=DB_POOL_SIZE,
        max_overflow=DB_MAX_OVERFLOW,
        pool_timeout=DB_POOL_TIMEOUT,
    )

SessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)


@asynccontextmanager
async def session_scope():
    session = SessionLocal()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


async def init_db_schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
