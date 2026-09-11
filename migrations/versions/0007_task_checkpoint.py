"""task_checkpoint

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-03
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: Sequence[str] | str | None = None
depends_on: Sequence[str] | str | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE task_checkpoint (
            task_ref              TEXT PRIMARY KEY,
            stage                 TEXT NOT NULL,
            objective             TEXT NOT NULL DEFAULT '',
            context_space_ids     JSONB NOT NULL DEFAULT '[]',
            accepted_decisions    JSONB NOT NULL DEFAULT '[]',
            completed_actions     JSONB NOT NULL DEFAULT '[]',
            files_changed         JSONB NOT NULL DEFAULT '[]',
            tests_executed        JSONB NOT NULL DEFAULT '[]',
            unresolved_questions  JSONB NOT NULL DEFAULT '[]',
            evidence_versions     JSONB NOT NULL DEFAULT '{}',
            repository_sha        TEXT NULL,
            updated_at             TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE task_checkpoint")
