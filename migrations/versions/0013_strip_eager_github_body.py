"""strip eagerly-stored PR/Issue body from github node attributes

Revision ID: 0013
Revises: 0012
Create Date: 2026-09-09

connectors/github/mapper.py's map_pull_request and map_issue used to
duplicate the full PR/Issue body (one real example ran 17.7KB) into every
synced node's `attributes`, even though get_content() now exposes it on
demand — the same ADR-003 violation 0011 fixed for Azure DevOps work items.
Fixed in code alongside this migration (get_content() also gained the
on-demand path for PR/Issue native_ids, which it never had before — the
body was previously reachable ONLY as eagerly-stored attribute data).

This was already applied by hand via a one-off UPDATE earlier in this
project's life, which fixed the live database but was never captured as a
migration — meaning it silently would not have survived a fresh
environment (a full migration replay would leave the bodies back in place,
since content_hash is unchanged by this fix and a plain re-sync would skip
the rewrite, per the same trap 0010/0011/0012 document). This migration
makes that fix reproducible. Idempotent against an environment where the
manual fix already ran — the WHERE clause simply matches nothing there.
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: Sequence[str] | str | None = None
depends_on: Sequence[str] | str | None = None


def upgrade() -> None:
    # Postgres-only JSONB operators, and moot on SQLite regardless: a
    # fresh SQLite database reaching this migration was never synced by
    # the pre-fix mapper this backfills for. Same reasoning as 0010/0011/0012.
    if op.get_bind().dialect.name == "sqlite":
        return
    op.execute(
        """
        UPDATE node
        SET attributes = attributes - 'body'
        WHERE layer = 'TECHNICAL'
          AND source_system = 'github'
          AND kind IN ('PULL_REQUEST', 'ISSUE')
          AND attributes ? 'body'
        """
    )


def downgrade() -> None:
    # Deliberately a no-op: the stripped body text isn't retained anywhere
    # to restore, and it was never authoritative here anyway — get_content()
    # reads it straight from GitHub on demand, unaffected by this migration
    # in either direction (same reasoning as 0011's downgrade).
    pass
