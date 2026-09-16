"""EdgeRepository."""

from __future__ import annotations

from datetime import datetime
from typing import cast
from uuid import UUID

from sqlalchemy import CursorResult, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from context_fabric.domain.edge import Edge
from context_fabric.domain.enums import EdgeOrigin, EdgeState, EdgeType
from context_fabric.persistence.orm.edge import EdgeORM


def _to_domain(row: EdgeORM) -> Edge:
    return Edge(
        id=row.id,
        src_id=row.src_id,
        dst_id=row.dst_id,
        type=EdgeType(row.type),
        origin=EdgeOrigin(row.origin),
        confidence=row.confidence,
        state=EdgeState(row.state),
        evidence_id=row.evidence_id,
        attributes=row.attributes,
        first_seen_at=row.first_seen_at,
        last_seen_at=row.last_seen_at,
        deleted_at=row.deleted_at,
    )


class EdgeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, edge: Edge) -> Edge:
        row = EdgeORM(
            id=edge.id,
            src_id=edge.src_id,
            dst_id=edge.dst_id,
            type=edge.type.value,
            origin=edge.origin.value,
            confidence=edge.confidence,
            state=edge.state.value,
            evidence_id=edge.evidence_id,
            attributes=edge.attributes,
            first_seen_at=edge.first_seen_at,
            last_seen_at=edge.last_seen_at,
            deleted_at=edge.deleted_at,
        )
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return _to_domain(row)

    async def get(self, edge_id: UUID) -> Edge | None:
        row = await self._session.get(EdgeORM, edge_id)
        return _to_domain(row) if row is not None else None

    async def get_by_identity(
        self, src_id: UUID, dst_id: UUID, edge_type: str, origin: str
    ) -> Edge | None:
        stmt = select(EdgeORM).where(
            EdgeORM.src_id == src_id,
            EdgeORM.dst_id == dst_id,
            EdgeORM.type == edge_type,
            EdgeORM.origin == origin,
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return _to_domain(row) if row is not None else None

    async def list_from(self, src_id: UUID, *, exclude_deleted: bool = True) -> list[Edge]:
        stmt = select(EdgeORM).where(EdgeORM.src_id == src_id)
        if exclude_deleted:
            stmt = stmt.where(EdgeORM.deleted_at.is_(None))
        rows = (await self._session.execute(stmt)).scalars().all()
        return [_to_domain(r) for r in rows]

    async def list_touching(
        self, node_id: UUID, *, exclude_types: list[str] | None = None
    ) -> list[Edge]:
        """Every edge with `node_id` on either end (docs/UI.md "Catalog
        Explorer" Hierarchy tab's dependencies) — CONTAINS excluded by
        default via exclude_types, since that's the structural tree
        already shown separately; this is for MENTIONS/RELATED_TO."""
        stmt = select(EdgeORM).where(
            or_(EdgeORM.src_id == node_id, EdgeORM.dst_id == node_id),
            EdgeORM.deleted_at.is_(None),
        )
        if exclude_types:
            stmt = stmt.where(EdgeORM.type.notin_(exclude_types))
        rows = (await self._session.execute(stmt)).scalars().all()
        return [_to_domain(r) for r in rows]

    async def soft_delete(self, edge_id: UUID, deleted_at: datetime) -> None:
        row = await self._session.get(EdgeORM, edge_id)
        if row is not None:
            row.deleted_at = deleted_at
            await self._session.flush()

    async def soft_delete_touching(self, node_id: UUID, deleted_at: datetime) -> int:
        """Soft-deletes every still-active edge with `node_id` on either
        end — a tombstoned node (synchronization/orchestrator.py) must
        never leave dangling edges pointing at it; node.soft_delete alone
        only marks the node row itself. One bulk UPDATE rather than
        loading rows first, since a tombstoned node touching hundreds of
        edges is a real case (a shared container going away)."""
        stmt = (
            update(EdgeORM)
            .where(
                or_(EdgeORM.src_id == node_id, EdgeORM.dst_id == node_id),
                EdgeORM.deleted_at.is_(None),
            )
            .values(deleted_at=deleted_at)
        )
        result = await self._session.execute(stmt)
        await self._session.flush()
        return cast(CursorResult, result).rowcount or 0

    async def list_by_state(
        self, state: str, *, edge_types: list[str] | None = None, limit: int = 200
    ) -> list[Edge]:
        """Every edge in a given state (docs/UI.md "Proposed links review
        queue" — `state=PROPOSED` is the review queue itself), optionally
        narrowed to specific edge types."""
        stmt = select(EdgeORM).where(
            EdgeORM.state == state, EdgeORM.deleted_at.is_(None)
        )
        if edge_types:
            stmt = stmt.where(EdgeORM.type.in_(edge_types))
        stmt = stmt.order_by(EdgeORM.first_seen_at.desc()).limit(limit)
        rows = (await self._session.execute(stmt)).scalars().all()
        return [_to_domain(r) for r in rows]

    async def set_state(self, edge_id: UUID, state: str, now: datetime) -> Edge | None:
        row = await self._session.get(EdgeORM, edge_id)
        if row is None:
            return None
        row.state = state
        row.last_seen_at = now
        await self._session.flush()
        await self._session.refresh(row)
        return _to_domain(row)

    async def set_state_bulk(self, edge_ids: list[UUID], state: str, now: datetime) -> list[Edge]:
        """Same transition as set_state, applied to many rows in one
        flush instead of one round trip per row — the review queue's bulk
        confirm/reject action (docs/UI.md "Proposed links review queue").
        A missing/already-deleted id is silently skipped rather than
        failing the whole batch, since the caller's selection may be
        stale by the time this runs (another reviewer acted first)."""
        updated: list[EdgeORM] = []
        for edge_id in edge_ids:
            row = await self._session.get(EdgeORM, edge_id)
            if row is None:
                continue
            row.state = state
            row.last_seen_at = now
            updated.append(row)
        await self._session.flush()
        return [_to_domain(row) for row in updated]

    async def retype_dst(self, edge_id: UUID, dst_id: UUID, now: datetime) -> Edge | None:
        """A human picked a different target than what was proposed
        (e.g. a different team) — updates the edge in place and confirms
        it, rather than requiring reject-then-recreate."""
        row = await self._session.get(EdgeORM, edge_id)
        if row is None:
            return None
        row.dst_id = dst_id
        row.state = EdgeState.ACTIVE.value
        row.last_seen_at = now
        await self._session.flush()
        await self._session.refresh(row)
        return _to_domain(row)

    async def list_touching_any(
        self, node_ids: list[UUID], *, exclude_types: list[str] | None = None
    ) -> list[Edge]:
        """Every edge with at least one end in `node_ids` — the batched
        form of list_touching, for "every real cross-reference out of this
        whole subtree, not just its root" (docs/UI.md "Catalog Explorer"
        full-graph view). Unlike list_among, this deliberately *does*
        include edges to something outside `node_ids` — that's the whole
        point: a cross-vendor MENTIONS/IMPLEMENTS edge always points
        outside a node's own path-subtree (different source system means
        a completely different path tree), so list_among alone can never
        surface it."""
        if not node_ids:
            return []
        stmt = select(EdgeORM).where(
            or_(EdgeORM.src_id.in_(node_ids), EdgeORM.dst_id.in_(node_ids)),
            EdgeORM.deleted_at.is_(None),
        )
        if exclude_types:
            stmt = stmt.where(EdgeORM.type.notin_(exclude_types))
        rows = (await self._session.execute(stmt)).scalars().all()
        return [_to_domain(r) for r in rows]

    async def list_among(self, node_ids: list[UUID]) -> list[Edge]:
        """Every edge whose src AND dst are both within `node_ids`
        (docs/UI.md "Catalog Explorer" full-graph view) — the edge set for
        a rendered subgraph, so a link to something outside the visible
        node set never appears as a dangling reference."""
        if not node_ids:
            return []
        stmt = select(EdgeORM).where(
            EdgeORM.src_id.in_(node_ids),
            EdgeORM.dst_id.in_(node_ids),
            EdgeORM.deleted_at.is_(None),
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [_to_domain(r) for r in rows]
