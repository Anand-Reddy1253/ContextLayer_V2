"""indexes for the entity query language

Revision ID: 0014
Revises: 0013
Create Date: 2026-09-14

The entity query grammar (domain/query.py, compiled by
retrieval/query_compiler.py) filters on two things the `node` table has no
index for at all:

1. **`attributes` JSONB.** Every bare property in a query ("state", "priority",
   "assigned_to", "created_at") compiles to `attributes ->> :key`. There was no
   index on `attributes` of any kind, so each one was a sequential scan.
   `jsonb_path_ops` is the smaller, faster variant and covers containment,
   which is what these lookups reduce to.

2. **`name` for substring matching.** `contains`/`beginsWith`/`endsWith`
   compile to ILIKE, and a leading-wildcard ILIKE cannot use a btree index —
   confirmed by EXPLAIN on the existing search endpoint, which showed a
   `Seq Scan on node` filtering `name ~~* '%vacancy%'`. A trigram GIN index is
   the standard answer and serves all three operators.

`path` needs nothing new: "beginsWith" on a path compiles to ltree's `<@`,
which `ix_node_path_gist` (migration 0002) already covers.
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: Sequence[str] | str | None = None
depends_on: Sequence[str] | str | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_node_attributes_gin "
        "ON node USING GIN (attributes jsonb_path_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_node_name_trgm ON node USING GIN (name gin_trgm_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_node_name_trgm")
    op.execute("DROP INDEX IF EXISTS ix_node_attributes_gin")
    # pg_trgm is deliberately left installed — dropping a database-wide
    # extension because one index went away could break anything else that
    # started relying on it.
