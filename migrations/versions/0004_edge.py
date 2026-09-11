"""edge

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-03

Ordered after evidence (0003), not combined with node (0002) as
migrations/README.md originally sketched — edge.evidence_id references
evidence(id), so evidence must exist first. Noted as a deliberate
deviation from the Phase 0 sketch, per docs/phases/PHASE-02.md's
acceptance criteria ("any necessary deviation is called out, not silently
made").
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: Sequence[str] | str | None = None
depends_on: Sequence[str] | str | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE edge (
            id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            src_id        UUID NOT NULL REFERENCES node(id),
            dst_id        UUID NOT NULL REFERENCES node(id),
            type          TEXT NOT NULL CHECK (type IN (
                              'CONTAINS','BELONGS_TO','OWNED_BY','HAS_SERVICE',
                              'IMPLEMENTED_BY','SPECIFIED_BY','IMPLEMENTS','CHANGES',
                              'VERIFIES','DEPENDS_ON','MENTIONS','RELATED_TO')),
            origin        TEXT NOT NULL CHECK (origin IN
                              ('SYNC_STRUCTURAL','SYNC_EXTRACTED','HUMAN','RULE')),
            confidence    REAL NOT NULL DEFAULT 1.0,
            state         TEXT NOT NULL DEFAULT 'ACTIVE'
                              CHECK (state IN ('ACTIVE','PROPOSED','REJECTED')),
            evidence_id   UUID NULL REFERENCES evidence(id),
            attributes    JSONB NOT NULL DEFAULT '{}',
            first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            last_seen_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            deleted_at    TIMESTAMPTZ NULL
        )
        """
    )
    op.execute("CREATE UNIQUE INDEX ux_edge_identity ON edge (src_id, dst_id, type, origin)")
    op.execute("CREATE INDEX ix_edge_src ON edge (src_id, type) WHERE deleted_at IS NULL")
    op.execute("CREATE INDEX ix_edge_dst ON edge (dst_id, type) WHERE deleted_at IS NULL")
    op.execute("CREATE INDEX ix_edge_state ON edge (state) WHERE state = 'PROPOSED'")


def downgrade() -> None:
    op.execute("DROP TABLE edge")
