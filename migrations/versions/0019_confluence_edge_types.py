"""widen edge.type check constraint for Confluence relationship extraction

Revision ID: 0019
Revises: 0018
Create Date: 2026-09-16

Adds IN_SPACE, AUTHORED_BY, COMMENTED_ON, LINKS_TO, TRANSCLUDES, HAS_LABEL
to the `edge.type` CHECK constraint (migration 0004's own inline check,
"edge_type_check" on Postgres) — domain/enums.py's EdgeType enum was the
easy half of adding these; the DB's own constraint is a second, separate
source of truth that must be widened too, or every one of these edges
fails at insert time with a CheckViolation (confirmed live: this is
exactly what happened before this migration existed).

Postgres supports dropping/re-adding a named CHECK constraint directly.
SQLite has no ALTER TABLE ... DROP CONSTRAINT at all — widening a CHECK
there means the standard SQLite migration pattern: build a new table with
the wider constraint, copy every row, drop the old table, rename the new
one into place, recreate its indexes.
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: Sequence[str] | str | None = None
depends_on: Sequence[str] | str | None = None

_NEW_TYPE_LIST = (
    "'CONTAINS','BELONGS_TO','OWNED_BY','HAS_SERVICE',"
    "'IMPLEMENTED_BY','SPECIFIED_BY','IMPLEMENTS','CHANGES',"
    "'VERIFIES','DEPENDS_ON','MENTIONS','RELATED_TO',"
    "'IN_SPACE','AUTHORED_BY','COMMENTED_ON','LINKS_TO',"
    "'TRANSCLUDES','HAS_LABEL'"
)

_OLD_TYPE_LIST = (
    "'CONTAINS','BELONGS_TO','OWNED_BY','HAS_SERVICE',"
    "'IMPLEMENTED_BY','SPECIFIED_BY','IMPLEMENTS','CHANGES',"
    "'VERIFIES','DEPENDS_ON','MENTIONS','RELATED_TO'"
)

_NEW_ONLY_TYPE_LIST = (
    "'IN_SPACE','AUTHORED_BY','COMMENTED_ON','LINKS_TO','TRANSCLUDES','HAS_LABEL'"
)


def _recreate_indexes() -> None:
    """Same index set migration 0004 created. Indexes are dropped along
    with the table on both dialects (SQLite's rebuild via DROP TABLE,
    Postgres's constraint swap doesn't touch them — but recreating
    unconditionally is harmless and keeps this correct even if that
    assumption ever changes)."""
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_edge_identity "
        "ON edge (src_id, dst_id, type, origin)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_edge_src ON edge (src_id, type) WHERE deleted_at IS NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_edge_dst ON edge (dst_id, type) WHERE deleted_at IS NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_edge_state ON edge (state) WHERE state = 'PROPOSED'"
    )


def upgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        op.execute(
            f"""
            CREATE TABLE edge_new (
                id            TEXT PRIMARY KEY,
                src_id        TEXT NOT NULL REFERENCES node(id),
                dst_id        TEXT NOT NULL REFERENCES node(id),
                type          TEXT NOT NULL CHECK (type IN ({_NEW_TYPE_LIST})),
                origin        TEXT NOT NULL CHECK (origin IN
                                  ('SYNC_STRUCTURAL','SYNC_EXTRACTED','HUMAN','RULE')),
                confidence    REAL NOT NULL DEFAULT 1.0,
                state         TEXT NOT NULL DEFAULT 'ACTIVE'
                                  CHECK (state IN ('ACTIVE','PROPOSED','REJECTED')),
                evidence_id   TEXT NULL REFERENCES evidence(id),
                attributes    TEXT NOT NULL DEFAULT '{{}}',
                first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                last_seen_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                deleted_at    TEXT NULL
            )
            """
        )
        op.execute(
            "INSERT INTO edge_new SELECT id, src_id, dst_id, type, origin, confidence, "
            "state, evidence_id, attributes, first_seen_at, last_seen_at, deleted_at FROM edge"
        )
        op.execute("DROP TABLE edge")
        op.execute("ALTER TABLE edge_new RENAME TO edge")
    else:
        op.execute("ALTER TABLE edge DROP CONSTRAINT edge_type_check")
        op.execute(
            f"ALTER TABLE edge ADD CONSTRAINT edge_type_check CHECK (type IN ({_NEW_TYPE_LIST}))"
        )

    _recreate_indexes()


def downgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        op.execute(
            f"""
            CREATE TABLE edge_old (
                id            TEXT PRIMARY KEY,
                src_id        TEXT NOT NULL REFERENCES node(id),
                dst_id        TEXT NOT NULL REFERENCES node(id),
                type          TEXT NOT NULL CHECK (type IN ({_OLD_TYPE_LIST})),
                origin        TEXT NOT NULL CHECK (origin IN
                                  ('SYNC_STRUCTURAL','SYNC_EXTRACTED','HUMAN','RULE')),
                confidence    REAL NOT NULL DEFAULT 1.0,
                state         TEXT NOT NULL DEFAULT 'ACTIVE'
                                  CHECK (state IN ('ACTIVE','PROPOSED','REJECTED')),
                evidence_id   TEXT NULL REFERENCES evidence(id),
                attributes    TEXT NOT NULL DEFAULT '{{}}',
                first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                last_seen_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                deleted_at    TEXT NULL
            )
            """
        )
        op.execute(
            "INSERT INTO edge_old SELECT id, src_id, dst_id, type, origin, confidence, "
            "state, evidence_id, attributes, first_seen_at, last_seen_at, deleted_at "
            f"FROM edge WHERE type NOT IN ({_NEW_ONLY_TYPE_LIST})"
        )
        op.execute("DROP TABLE edge")
        op.execute("ALTER TABLE edge_old RENAME TO edge")
    else:
        op.execute("ALTER TABLE edge DROP CONSTRAINT edge_type_check")
        op.execute(
            f"ALTER TABLE edge ADD CONSTRAINT edge_type_check CHECK (type IN ({_OLD_TYPE_LIST}))"
        )
    _recreate_indexes()
