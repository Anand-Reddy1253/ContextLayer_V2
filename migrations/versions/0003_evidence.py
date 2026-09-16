"""evidence

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-03
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: Sequence[str] | str | None = None
depends_on: Sequence[str] | str | None = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        op.execute(
            """
            CREATE TABLE evidence (
                id                  TEXT PRIMARY KEY,
                node_id             TEXT NOT NULL REFERENCES node(id),
                source_system       TEXT NOT NULL,
                source_instance_id  TEXT NOT NULL,
                native_id           TEXT NOT NULL,
                source_version      TEXT NULL,
                uri                 TEXT NOT NULL,
                content_hash        TEXT NULL,
                acl_ref             TEXT NOT NULL DEFAULT '{}',
                retrieved_at        TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
    else:
        op.execute(
            """
            CREATE TABLE evidence (
                id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                node_id             UUID NOT NULL REFERENCES node(id),
                source_system       TEXT NOT NULL,
                source_instance_id  TEXT NOT NULL,
                native_id           TEXT NOT NULL,
                source_version      TEXT NULL,
                uri                 TEXT NOT NULL,
                content_hash        TEXT NULL,
                acl_ref             JSONB NOT NULL DEFAULT '{}',
                retrieved_at        TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
    op.execute("CREATE INDEX ix_evidence_node ON evidence (node_id)")


def downgrade() -> None:
    op.execute("DROP TABLE evidence")
