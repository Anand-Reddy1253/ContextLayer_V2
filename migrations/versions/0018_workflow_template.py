"""workflow_template and workflow_step

Revision ID: 0018
Revises: 0017
Create Date: 2026-09-15

A named, ordered sequence of steps a harness pulls and executes
(docs/MCP.md's "harness composition" note on resolve_scope) — each step a
specific AI_ASSET node picked from the catalog at author time. Same shape
as 0005's context_space + binding: a parent row, an ordered list of child
rows, no cross-table default on the parent FK (deleting a context space
should not silently vaporize its templates).
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: Sequence[str] | str | None = None
depends_on: Sequence[str] | str | None = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        op.execute(
            """
            CREATE TABLE workflow_template (
                id                 TEXT PRIMARY KEY,
                context_space_id   TEXT NOT NULL REFERENCES context_space(id),
                name               TEXT NOT NULL,
                description        TEXT NOT NULL DEFAULT '',
                status             TEXT NOT NULL DEFAULT 'active',
                created_at         TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at         TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        op.execute(
            """
            CREATE TABLE workflow_step (
                id                     TEXT PRIMARY KEY,
                workflow_template_id   TEXT NOT NULL
                                       REFERENCES workflow_template(id) ON DELETE CASCADE,
                "order"                INTEGER NOT NULL,
                source_system          TEXT NOT NULL,
                source_instance_id     TEXT NOT NULL,
                native_id              TEXT NOT NULL,
                label                  TEXT NOT NULL,
                vendor                 TEXT NOT NULL,
                asset_type             TEXT NOT NULL,
                instructions           TEXT NULL,
                created_at             TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at             TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
    else:
        op.execute(
            """
            CREATE TABLE workflow_template (
                id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                context_space_id   TEXT NOT NULL REFERENCES context_space(id),
                name               TEXT NOT NULL,
                description        TEXT NOT NULL DEFAULT '',
                status             TEXT NOT NULL DEFAULT 'active',
                created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        op.execute(
            """
            CREATE TABLE workflow_step (
                id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                workflow_template_id   UUID NOT NULL
                                       REFERENCES workflow_template(id) ON DELETE CASCADE,
                "order"                INT NOT NULL,
                source_system          TEXT NOT NULL,
                source_instance_id     TEXT NOT NULL,
                native_id              TEXT NOT NULL,
                label                  TEXT NOT NULL,
                vendor                 TEXT NOT NULL,
                asset_type             TEXT NOT NULL,
                instructions           TEXT NULL,
                created_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at             TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
    op.execute(
        "CREATE INDEX ix_workflow_template_context_space "
        "ON workflow_template (context_space_id)"
    )
    op.execute(
        "CREATE INDEX ix_workflow_step_template_order "
        'ON workflow_step (workflow_template_id, "order")'
    )


def downgrade() -> None:
    op.execute("DROP TABLE workflow_step")
    op.execute("DROP TABLE workflow_template")
