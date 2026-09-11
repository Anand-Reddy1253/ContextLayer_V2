"""strip eagerly-stored work item description from node attributes

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-04

connectors/azure_devops/mapper.py's map_work_item used to duplicate the
full raw-HTML System.Description into every synced node's `attributes`,
even though get_content()/map_content() already exposes it on demand —
violating ADR-003 (content fetched on demand only, never eagerly
stored). Fixed in code alongside this migration; this strips the
"description" key from every already-synced azure_devops technical
node's attributes, since a plain re-sync won't touch it (content_hash is
computed from ADO's raw fields, unchanged by this fix, so
synchronization/idempotency.py's upsert skips the write). Nothing is
lost — the full description is still fetchable on demand via
get_content(), unchanged by this migration.
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: Sequence[str] | str | None = None
depends_on: Sequence[str] | str | None = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE node
        SET attributes = attributes - 'description'
        WHERE layer = 'TECHNICAL'
          AND source_system = 'azure_devops'
          AND attributes ? 'description'
        """
    )


def downgrade() -> None:
    # Deliberately a no-op: the stripped description text isn't retained
    # anywhere to restore, and it was never authoritative here anyway —
    # get_content() reads it straight from ADO on demand, unaffected by
    # this migration in either direction.
    pass
