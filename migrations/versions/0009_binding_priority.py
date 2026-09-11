"""binding priority

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-03

Adds the priority column docs/RETRIEVAL.md's ambiguity tiebreak assumed
from the start but the original Phase 2 schema (also Phase 0 output)
omitted — Phase 9 (scope resolution) is the first thing that actually
needed it (docs/phases/PHASE-09.md).
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: Sequence[str] | str | None = None
depends_on: Sequence[str] | str | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE binding ADD COLUMN priority INT NOT NULL DEFAULT 0")


def downgrade() -> None:
    op.execute("ALTER TABLE binding DROP COLUMN priority")
