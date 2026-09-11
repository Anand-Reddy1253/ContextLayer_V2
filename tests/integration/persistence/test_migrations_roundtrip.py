"""Proves migrations are reversible/rerunnable, not just forward-tested
once (docs/phases/PHASE-02.md exit gate: `alembic downgrade base &&
alembic upgrade head` round-trips cleanly).

Runs downgrade-to-base then upgrade-to-head against the real database used
by every other integration test in this package. Safe to run alongside
them because no other test leaves committed data behind (db_session rolls
back via savepoint) — this test only manipulates schema, and always ends
back at `head`.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import create_async_engine

REPO_ROOT = Path(__file__).resolve().parents[3]

EXPECTED_TABLES = {
    "node",
    "edge",
    "evidence",
    "context_space",
    "binding",
    "sync_state",
    "sync_run",
    "task_checkpoint",
    "connector_connection",
}


def _alembic_config(database_url: str) -> Config:
    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "migrations"))
    cfg.set_main_option("sqlalchemy.url", database_url)
    return cfg


async def _table_names(database_url: str) -> set[str]:
    engine = create_async_engine(database_url)
    async with engine.connect() as conn:
        names = await conn.run_sync(lambda sync_conn: set(inspect(sync_conn).get_table_names()))
    await engine.dispose()
    return names


def test_downgrade_base_then_upgrade_head_round_trips(database_url: str):
    # Deliberately a plain sync test, not `async def`: alembic's
    # command.downgrade/upgrade each call asyncio.run() internally
    # (migrations/env.py). Calling them from inside pytest-asyncio's own
    # running event loop raises "asyncio.run() cannot be called from a
    # running event loop" — an integration test caught this too.
    cfg = _alembic_config(database_url)

    command.downgrade(cfg, "base")
    after_downgrade = asyncio.run(_table_names(database_url))
    assert after_downgrade.isdisjoint(EXPECTED_TABLES)

    command.upgrade(cfg, "head")
    after_upgrade = asyncio.run(_table_names(database_url))
    assert EXPECTED_TABLES <= after_upgrade
