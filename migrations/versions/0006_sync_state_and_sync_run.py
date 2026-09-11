"""sync_state and sync_run

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-03
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: Sequence[str] | str | None = None
depends_on: Sequence[str] | str | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE sync_state (
            source_system         TEXT NOT NULL,
            scope_id               TEXT NOT NULL,
            cursor                  TEXT NULL,
            last_event_id           TEXT NULL,
            last_successful_sync    TIMESTAMPTZ NULL,
            last_reconciliation     TIMESTAMPTZ NULL,
            status                   TEXT NOT NULL DEFAULT 'PENDING',
            error                    TEXT NULL,
            PRIMARY KEY (source_system, scope_id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE sync_run (
            id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            source_system     TEXT NOT NULL,
            scope_id          TEXT NOT NULL,
            correlation_id    TEXT NOT NULL,
            started_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
            finished_at       TIMESTAMPTZ NULL,
            status            TEXT NOT NULL DEFAULT 'RUNNING',
            nodes_upserted    INT NOT NULL DEFAULT 0,
            nodes_tombstoned  INT NOT NULL DEFAULT 0,
            edges_created     INT NOT NULL DEFAULT 0,
            error_category    TEXT NULL,
            error_detail      TEXT NULL
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_sync_run_scope ON sync_run (source_system, scope_id, started_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE sync_run")
    op.execute("DROP TABLE sync_state")
