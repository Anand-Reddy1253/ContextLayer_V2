"""Shared pytest fixtures — Postgres-backed, used by tests/integration/
and tests/acceptance/ alike (both need a real database; tests/unit/ never
touches this file's fixtures at all).

Requires CF_DATABASE_URL pointing at a reachable, migratable Postgres
(docker-compose.yml's `postgres` service, or an equivalent local
instance — see docs/PROGRESS.md's Phase 2 entry for how this repo's dev
machine works around Docker/WSL being unavailable).

Migration only happens lazily, once per test session, the first time a
test actually requests `db_session` — deliberately NOT a session-scoped
autouse fixture, so a `pytest tests/unit` run never touches Postgres at
all (docs/CONVENTIONS.md "Test layout": unit tests have zero I/O). Each
test then runs inside a savepoint that's rolled back on teardown, so
tests never see each other's data and the database doesn't accumulate
test fixtures across runs.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from context_fabric.settings import Settings

# psycopg3's async mode requires a SelectorEventLoop; Windows defaults to
# ProactorEventLoop, which it explicitly rejects. Must be set before
# pytest-asyncio creates its event loop.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def database_url() -> str:
    return Settings().CF_DATABASE_URL


@pytest.fixture(scope="session")
def _migrated_schema(database_url: str) -> None:
    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "migrations"))
    cfg.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(cfg, "head")


@pytest_asyncio.fixture
async def db_session(database_url: str, _migrated_schema: None):  # noqa: ANN201
    engine = create_async_engine(database_url)
    async with engine.connect() as conn:
        await conn.begin()
        async with AsyncSession(
            bind=conn, join_transaction_mode="create_savepoint"
        ) as session:
            yield session
        await conn.rollback()
    await engine.dispose()


@pytest.fixture
def now() -> datetime:
    return datetime.now(UTC)
