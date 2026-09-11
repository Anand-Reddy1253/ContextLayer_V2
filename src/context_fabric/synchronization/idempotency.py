"""Idempotent upsert logic — the content_hash comparison that makes
running sync twice with no source changes produce zero net graph change
(docs/phases/PHASE-06.md's idempotency gate). Isolated here, separate
from orchestrator.py's traversal logic, so Phase 7's link extraction can
reuse the same skip-if-unchanged pattern for edges.
"""

from __future__ import annotations

from dataclasses import dataclass

from context_fabric.domain.edge import Edge
from context_fabric.domain.node import Node
from context_fabric.persistence.repositories.edge import EdgeRepository
from context_fabric.persistence.repositories.node import NodeRepository


@dataclass
class NodeUpsertResult:
    node: Node
    created: bool
    updated: bool

    @property
    def changed(self) -> bool:
        return self.created or self.updated


async def upsert_node(node_repo: NodeRepository, candidate: Node) -> NodeUpsertResult:
    """Looks up `candidate` by its (source_system, source_instance_id,
    native_id) technical identity. Creates if absent. If found and
    content_hash matches, issues no write at all — not even a touch —
    and returns the existing row unchanged. Otherwise updates in place,
    keeping the existing row's id and bumping version."""
    existing = await node_repo.get_by_technical_identity(
        candidate.source_system,  # type: ignore[arg-type]
        candidate.source_instance_id,  # type: ignore[arg-type]
        candidate.native_id,  # type: ignore[arg-type]
    )
    if existing is None:
        created = await node_repo.create(candidate)
        return NodeUpsertResult(node=created, created=True, updated=False)

    if existing.content_hash == candidate.content_hash and existing.deleted_at is None:
        return NodeUpsertResult(node=existing, created=False, updated=False)

    to_update = candidate.model_copy(update={"id": existing.id, "version": existing.version + 1})
    updated = await node_repo.update(to_update)
    return NodeUpsertResult(node=updated, created=False, updated=True)


async def upsert_edge(edge_repo: EdgeRepository, candidate: Edge) -> bool:
    """Returns True if a new edge was created, False if an edge with the
    same (src_id, dst_id, type, origin) identity already existed (skip,
    no write) — the uniqueness constraint this mirrors is
    ux_edge_identity (docs/persistence.md)."""
    existing = await edge_repo.get_by_identity(
        candidate.src_id, candidate.dst_id, candidate.type.value, candidate.origin.value
    )
    if existing is not None:
        return False
    await edge_repo.create(candidate)
    return True
