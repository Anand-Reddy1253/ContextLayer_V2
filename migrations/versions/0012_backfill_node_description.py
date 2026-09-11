"""backfill node.description from attributes, and from real vendor data

Revision ID: 0012
Revises: 0011
Create Date: 2026-09-09

`node.description` has been NULL on every technical node since the schema
was built — `SourceObject`/`SourceContainer` (domain/connector_types.py)
never had a `description` field, so no connector could ever populate it,
even though ADR-003 already lists description as intended metadata. Fixed
in code alongside this migration (connectors now populate it directly,
moved out of `attributes` rather than duplicated). Two things this
migration does, since an unchanged node's content_hash means a plain
re-sync will not rewrite most of these rows
(synchronization/idempotency.py's upsert skips unchanged content — the same
trap documented in 0010 and 0011):

1. Backfills `description` from whatever a prior sync already stashed in
   `attributes->>'description'` (GitHub repos, GitHub AI assets, Azure
   DevOps projects) — real data already sitting in the database, just in
   the wrong column.
2. Strips the now-duplicated `description` key back out of `attributes`
   for those same rows, so the value has exactly one home going forward —
   same cleanup pattern as 0011.

Confluence SPACE descriptions are not covered here: the live connector
was fetching them with the wrong request shape (Confluence's v2 API
returns description=None unless asked for a format explicitly) and never
had real values to backfill from; the code fix pulls them fresh on the
next sync instead.
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: Sequence[str] | str | None = None
depends_on: Sequence[str] | str | None = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE node
        SET description = left(attributes->>'description', 512)
        WHERE layer = 'TECHNICAL'
          AND description IS NULL
          AND coalesce(attributes->>'description', '') <> ''
        """
    )
    op.execute(
        """
        UPDATE node
        SET attributes = attributes - 'description'
        WHERE layer = 'TECHNICAL'
          AND attributes ? 'description'
        """
    )


def downgrade() -> None:
    # Deliberately a no-op: the values moved from attributes into
    # description are still present (in description), nothing is lost;
    # reversing would require re-duplicating description back into
    # attributes for no benefit, same reasoning as 0010/0011.
    pass
