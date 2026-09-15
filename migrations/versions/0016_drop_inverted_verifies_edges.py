"""remove VERIFIES edges that point from the work item to the test case

Revision ID: 0016
Revises: 0015
Create Date: 2026-09-14

`connectors/azure_devops/mapper.py` mapped Azure DevOps's
`Microsoft.VSTS.Common.TestedBy-Forward` relation to link_kind "verifies" and
emitted it *from* the work item. That relation sits on the work item and names
the test case, so it reads "this work item is tested by that test case" — which
means the test case verifies the work item, not the reverse. Emitted forward it
produced 93 edges reading `STORY --VERIFIES--> TEST_CASE`, every one pointing
the wrong way.

Fixed in code alongside this migration: SourceLink gained a `reverse` flag and
link_extraction.py swaps the endpoints when it is set, so a re-sync now creates
the correct `TEST_CASE --VERIFIES--> STORY` edges.

A re-sync does not remove the old ones. Edge identity is
(src_id, dst_id, type, origin), so swapping the endpoints produces a *new*
edge rather than updating the existing row, and `upsert_edge` never deletes
edges that stop being produced — the same behaviour that left duplicate
CONTAINS edges behind when test-hierarchy re-parenting landed. This deletes the
inverted rows, identified by their endpoint kinds.

Worth removing rather than leaving: the entity query language added in this
change exposes `relatedTo` with a direction, so a caller asking "what verifies
this story?" would get the story's own test cases *and* the story itself back.
A confidently wrong traversal is worse than a missing one.
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: Sequence[str] | str | None = None
depends_on: Sequence[str] | str | None = None

_TEST_KINDS = "('TEST_CASE', 'TEST_SUITE', 'TEST_PLAN')"


def upgrade() -> None:
    # Only the inverted direction: source is a work item, target is a test.
    op.execute(
        f"""
        DELETE FROM edge e
        USING node src, node dst
        WHERE e.src_id = src.id
          AND e.dst_id = dst.id
          AND e.type = 'VERIFIES'
          AND src.kind NOT IN {_TEST_KINDS}
          AND dst.kind IN {_TEST_KINDS}
        """
    )


def downgrade() -> None:
    # Deliberately a no-op: these rows asserted a relationship that was
    # backwards, so recreating them would only reintroduce the bug. The
    # correct edges are produced by sync — same reasoning as 0011-0013.
    pass
