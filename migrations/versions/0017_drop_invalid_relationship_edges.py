"""remove extracted edges that violate configs/relationships.yaml

Revision ID: 0017
Revises: 0016
Create Date: 2026-09-15

Before this change, `link_extraction.py` had no domain/range check: a
work-item id found in a pull request's *title* was typed IMPLEMENTS purely
from where it was found, with nothing verifying the referencing node was
actually a pull request or commit. Three ADO work items whose own titles
happened to contain "AB#NNN" (referencing a sibling work item, not a real
implementation relationship) produced STORY --IMPLEMENTS--> STORY edges.

Fixed in code alongside this migration: `synchronization/link_extraction.py`
now checks every extracted (SYNC_EXTRACTED) edge against
`configs/relationships.yaml` via `domain/config.py`'s `RelationshipsConfig`
before creating it, and a re-sync now correctly rejects new attempts at the
same three edges (confirmed live: `link_extraction.relationship_rejected`
logged for native_ids 443, 469, 470).

A re-sync does not remove the three edges that were already created under
the old, unchecked logic — the same content_hash-skip situation every
migration in this series exists for. This is a general cleanup, not scoped
to one relation type the way 0016 was for VERIFIES: it removes *any*
still-active extracted edge that the now-loaded rules would reject, so a
future rule tightening doesn't need its own bespoke migration for edges
that predate it.
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
from sqlalchemy import bindparam, text

from context_fabric.domain.config import load_relationships
from context_fabric.domain.enums import EdgeType

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: Sequence[str] | str | None = None
depends_on: Sequence[str] | str | None = None

# Only extracted edges are subject to relationships.yaml at all — CONTAINS
# and other structural types never pass through link_extraction.py, so this
# migration only ever inspects these.
_EXTRACTED_TYPES = (
    EdgeType.VERIFIES,
    EdgeType.IMPLEMENTS,
    EdgeType.CHANGES,
    EdgeType.SPECIFIED_BY,
    EdgeType.DEPENDS_ON,
    EdgeType.RELATED_TO,
    EdgeType.MENTIONS,
)


def upgrade() -> None:
    rules = load_relationships()
    bind = op.get_bind()
    # Not `= ANY(:types)`/`= ANY(:ids)` — Postgres array-parameter syntax.
    # `IN :param` with an `expanding=True` bindparam is SQLAlchemy's
    # dialect-agnostic equivalent (same fix as graph/traversal.py's
    # recursive edge-type filter).
    select_stmt = text(
        """
        SELECT e.id, e.type, src.kind, dst.kind
        FROM edge e
        JOIN node src ON src.id = e.src_id
        JOIN node dst ON dst.id = e.dst_id
        WHERE e.deleted_at IS NULL
          AND e.origin IN ('SYNC_EXTRACTED', 'SYNC_STRUCTURAL')
          AND e.type IN :types
        """
    ).bindparams(bindparam("types", expanding=True))
    rows = bind.execute(
        select_stmt, {"types": [t.value for t in _EXTRACTED_TYPES]}
    ).fetchall()

    to_delete = [
        str(edge_id)
        for edge_id, edge_type, src_kind, dst_kind in rows
        if not rules.allows(EdgeType(edge_type), src_kind, dst_kind)
    ]
    if to_delete:
        delete_stmt = text("DELETE FROM edge WHERE id IN :ids").bindparams(
            bindparam("ids", expanding=True)
        )
        bind.execute(delete_stmt, {"ids": to_delete})
    print(f"0017: removed {len(to_delete)} edge(s) violating configs/relationships.yaml")


def downgrade() -> None:
    # Deliberately a no-op: these edges were invalid under the declared
    # rules, so recreating them would only reintroduce the bug. Correct
    # edges are produced by sync — same reasoning as 0011-0013, 0016.
    pass
