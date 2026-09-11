"""connector_connection

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-03
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: Sequence[str] | str | None = None
depends_on: Sequence[str] | str | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE connector_connection (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            source_system       TEXT NOT NULL,
            instance_id         TEXT NOT NULL,
            display_name        TEXT NOT NULL,
            mode                TEXT NOT NULL DEFAULT 'fixture',
            config              JSONB NOT NULL DEFAULT '{}',
            credential_ciphertext BYTEA NULL,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX ux_connector_connection_identity
            ON connector_connection (source_system, instance_id)
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE connector_connection")
