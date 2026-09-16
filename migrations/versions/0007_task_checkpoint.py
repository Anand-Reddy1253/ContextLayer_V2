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
    is_sqlite = op.get_bind().dialect.name == "sqlite"
    json_type = "TEXT" if is_sqlite else "JSONB"
    ts_type = "TEXT" if is_sqlite else "TIMESTAMPTZ"
    ts_default = "DEFAULT CURRENT_TIMESTAMP" if is_sqlite else "DEFAULT now()"

    op.execute(
        f"""
        CREATE TABLE task_checkpoint (
            task_ref              TEXT PRIMARY KEY,
            stage                 TEXT NOT NULL,
            objective             TEXT NOT NULL DEFAULT '',
            context_space_ids     {json_type} NOT NULL DEFAULT '[]',
            accepted_decisions    {json_type} NOT NULL DEFAULT '[]',
            completed_actions     {json_type} NOT NULL DEFAULT '[]',
            files_changed         {json_type} NOT NULL DEFAULT '[]',
            tests_executed        {json_type} NOT NULL DEFAULT '[]',
            unresolved_questions  {json_type} NOT NULL DEFAULT '[]',
            evidence_versions     {json_type} NOT NULL DEFAULT '{{}}',
            repository_sha        TEXT NULL,
            updated_at             {ts_type} NOT NULL {ts_default}
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE task_checkpoint")
