"""context_space and binding

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-03
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: Sequence[str] | str | None = None
depends_on: Sequence[str] | str | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE context_space (
            id                 TEXT PRIMARY KEY,
            business_node_id   UUID NOT NULL REFERENCES node(id),
            name               TEXT NOT NULL,
            description        TEXT NOT NULL DEFAULT '',
            owners             JSONB NOT NULL DEFAULT '[]',
            product            TEXT NULL,
            teams              JSONB NOT NULL DEFAULT '[]',
            services           JSONB NOT NULL DEFAULT '[]',
            status             TEXT NOT NULL DEFAULT 'active',
            version            INT NOT NULL DEFAULT 1,
            created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE binding (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            context_space_id    TEXT NOT NULL REFERENCES context_space(id) ON DELETE CASCADE,
            capability          TEXT NOT NULL,
            source_system       TEXT NOT NULL,
            source_instance_id  TEXT NOT NULL,
            native_container    TEXT NOT NULL,
            origin              TEXT NOT NULL DEFAULT 'HUMAN',
            created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX ix_binding_context_space ON binding (context_space_id)")
    op.execute(
        "CREATE INDEX ix_binding_lookup "
        "ON binding (source_system, source_instance_id, native_container)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE binding")
    op.execute("DROP TABLE context_space")
