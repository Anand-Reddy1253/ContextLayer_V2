"""extensions

Revision ID: 0001
Revises:
Create Date: 2026-09-03
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: Sequence[str] | str | None = None
depends_on: Sequence[str] | str | None = None


def upgrade() -> None:
    # Postgres-only — SQLite has no extension system and needs none of
    # these (pgcrypto's gen_random_uuid() is replaced by client-side UUID
    # generation via the ORM's Uuid column type; ltree by plain TEXT).
    if op.get_bind().dialect.name != "sqlite":
        op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
        op.execute("CREATE EXTENSION IF NOT EXISTS ltree")


def downgrade() -> None:
    if op.get_bind().dialect.name != "sqlite":
        op.execute("DROP EXTENSION IF EXISTS ltree")
        op.execute("DROP EXTENSION IF EXISTS pgcrypto")
