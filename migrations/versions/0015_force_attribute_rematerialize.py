"""force the next sync to rewrite nodes so new attributes land

Revision ID: 0015
Revises: 0014
Create Date: 2026-09-14

The connectors now capture vendor timestamps and the other fields a real
question filters on — `created_at`/`updated_at` on work items and pull
requests, plus `created_by`, `priority`, `iteration_path`, `tags`, `author`,
`is_draft`, `labels`. Measured coverage before this change: any timestamp at
all was present on 0/138 PULL_REQUEST, 0/106 STORY, 0/99 TASK and 0/9 BUG.

A code change alone will not backfill any of it. `synchronization/
idempotency.py`'s `upsert_node` skips the write entirely when `content_hash`
is unchanged, and `content_hash` is derived from the raw *vendor* payload —
which did not change, because the fields were always being fetched and simply
discarded in the mapper. So a plain re-sync would leave every existing row
exactly as it is. This is the same trap migrations 0010, 0011, 0012 and 0013
were each written for.

Unlike those, this one cannot fix the data itself: the new values live in the
vendor, not in a column we can copy from. What it can do is clear the hash so
the next sync sees every affected node as changed and rewrites it with the
full attribute set.

Scoped to the kinds whose mappers actually changed, so untouched parts of the
graph are not needlessly rewritten on the next run.
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: Sequence[str] | str | None = None
depends_on: Sequence[str] | str | None = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE node
        SET content_hash = NULL
        WHERE layer = 'TECHNICAL'
          AND deleted_at IS NULL
          AND kind IN (
            'STORY', 'TASK', 'BUG', 'FEATURE', 'EPIC', 'WORK_ITEM',
            'TEST_CASE', 'TEST_SUITE', 'TEST_PLAN',
            'PULL_REQUEST', 'ISSUE', 'PAGE'
          )
        """
    )


def downgrade() -> None:
    # Deliberately a no-op: the cleared hashes are recomputed by the next
    # sync from the vendor payload, so nothing is lost and there is nothing
    # meaningful to restore — same reasoning as 0010-0013's downgrades.
    pass
