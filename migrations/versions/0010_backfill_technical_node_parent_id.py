"""backfill technical node parent_id from ltree path

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-04

The sync orchestrator (synchronization/orchestrator.py) set a technical
node's `path` (ltree) on creation but never its `parent_id` column —
only `path` encoded the hierarchy, so anything querying by parent_id
directly (docs/UI.md "Catalog Explorer" Hierarchy tab's direct-children
list) found nothing even though the tree was fully there via path.
Fixed in code alongside this migration; this backfills every
already-synced technical node's parent_id from its own path, since an
unchanged node's content_hash means a plain re-sync would never rewrite
it (synchronization/idempotency.py's upsert skips unchanged content).
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: Sequence[str] | str | None = None
depends_on: Sequence[str] | str | None = None


def upgrade() -> None:
    # Postgres-only (nlevel()/subpath() are ltree functions, no SQLite
    # equivalent) *and* moot there regardless: this backfills rows synced
    # before a code fix that predates SQLite support entirely, so a fresh
    # SQLite database reaching this migration has no such rows to fix —
    # the code orchestrator.py backfills correctly already writes
    # parent_id going forward, on both backends.
    if op.get_bind().dialect.name == "sqlite":
        return
    op.execute(
        """
        UPDATE node AS child
        SET parent_id = parent.id
        FROM node AS parent
        WHERE child.parent_id IS NULL
          AND child.layer = 'TECHNICAL'
          AND nlevel(child.path) > 1
          AND parent.path = subpath(child.path, 0, nlevel(child.path) - 1)
        """
    )


def downgrade() -> None:
    # Deliberately a no-op: reversing this would re-break direct-children
    # lookups for every already-synced technical node with no offsetting
    # benefit — there is no schema to roll back, only a derived value to
    # (re-)compute, which upgrade() already does correctly from `path`.
    pass
