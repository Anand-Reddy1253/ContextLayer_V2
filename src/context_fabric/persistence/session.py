"""Async engine + session factory.

The one place `CF_DATABASE_URL` is read to build a live connection pool.
Repositories and callers get sessions from `session_scope()` / the FastAPI
dependency in api/deps.py (Phase 15) — nobody constructs an engine of
their own.
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import lru_cache

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from context_fabric.settings import Settings

# psycopg3's async mode requires a SelectorEventLoop; Windows defaults to
# ProactorEventLoop, which it explicitly rejects. Set at import time since
# this module is the common entrypoint for every async DB connection.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


@lru_cache(maxsize=1)
def get_engine() -> AsyncEngine:
    settings = Settings()
    return create_async_engine(settings.CF_DATABASE_URL, pool_pre_ping=True)


@lru_cache(maxsize=1)
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(bind=get_engine(), expire_on_commit=False)


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """One transaction per use: commits on clean exit, rolls back on
    exception. Every repository call and every API/MCP request handler
    should open exactly one of these, not share a long-lived session."""
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
