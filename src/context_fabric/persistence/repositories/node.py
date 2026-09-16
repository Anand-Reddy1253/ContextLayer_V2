"""NodeRepository.

Every method takes/returns context_fabric.domain.Node — never NodeORM — to
callers outside persistence/ (docs/phases/PHASE-02.md).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from context_fabric.domain.enums import Capability, Layer, NodeStatus
from context_fabric.domain.node import Node
from context_fabric.persistence.dialect_compat import path_contains
from context_fabric.persistence.orm.node import NodeORM


def _to_domain(row: NodeORM) -> Node:
    return Node(
        id=row.id,
        layer=Layer(row.layer),
        kind=row.kind,
        capability=Capability(row.capability) if row.capability else None,
        name=row.name,
        description=row.description,
        owners=row.owners,
        source_system=row.source_system,
        source_instance_id=row.source_instance_id,
        native_id=row.native_id,
        parent_id=row.parent_id,
        path=row.path,
        status=NodeStatus(row.status),
        version=row.version,
        source_version=row.source_version,
        content_hash=row.content_hash,
        acl_ref=row.acl_ref,
        attributes=row.attributes,
        first_seen_at=row.first_seen_at,
        last_seen_at=row.last_seen_at,
        deleted_at=row.deleted_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class NodeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, node: Node) -> Node:
        row = NodeORM(
            id=node.id,
            layer=node.layer.value,
            kind=node.kind,
            capability=node.capability.value if node.capability else None,
            name=node.name,
            description=node.description,
            owners=node.owners,
            source_system=node.source_system,
            source_instance_id=node.source_instance_id,
            native_id=node.native_id,
            parent_id=node.parent_id,
            path=node.path,
            status=node.status.value,
            version=node.version,
            source_version=node.source_version,
            content_hash=node.content_hash,
            acl_ref=node.acl_ref,
            attributes=node.attributes,
            first_seen_at=node.first_seen_at,
            last_seen_at=node.last_seen_at,
            deleted_at=node.deleted_at,
            created_at=node.created_at,
            updated_at=node.updated_at,
        )
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return _to_domain(row)

    async def get(self, node_id: UUID) -> Node | None:
        row = await self._session.get(NodeORM, node_id)
        return _to_domain(row) if row is not None else None

    async def list_by_layer(self, layer: Layer) -> list[Node]:
        stmt = (
            select(NodeORM)
            .where(NodeORM.layer == layer.value, NodeORM.deleted_at.is_(None))
            .order_by(NodeORM.path)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [_to_domain(r) for r in rows]

    async def get_by_path(self, path: str) -> Node | None:
        """Exact ltree path match — used by catalog/business_tree.py to
        resolve a human-readable business path (e.g.
        "ACME/Engineering/TalentFlow/Identity", dots substituted for
        slashes) to its node. Not enforced unique by a DB constraint;
        deterministic (first match) but only meaningful for the
        single-tenant business tree this project seeds today."""
        stmt = select(NodeORM).where(NodeORM.path == path)
        row = (await self._session.execute(stmt)).scalars().first()
        return _to_domain(row) if row is not None else None

    async def update(self, node: Node) -> Node:
        """Updates every mutable field of an existing row by `node.id`.
        Used by synchronization/idempotency.py when a technical node's
        content_hash has changed — never called for a node that doesn't
        already exist (see NodeRepository.create for that path)."""
        row = await self._session.get(NodeORM, node.id)
        if row is None:
            raise ValueError(f"cannot update: no node with id={node.id}")
        row.kind = node.kind
        row.capability = node.capability.value if node.capability else None
        row.name = node.name
        row.description = node.description
        row.owners = node.owners
        row.parent_id = node.parent_id
        row.path = node.path
        row.status = node.status.value
        row.version = node.version
        row.source_version = node.source_version
        row.content_hash = node.content_hash
        row.acl_ref = node.acl_ref
        row.attributes = node.attributes
        row.last_seen_at = node.last_seen_at
        row.deleted_at = node.deleted_at
        row.updated_at = node.updated_at
        await self._session.flush()
        await self._session.refresh(row)
        return _to_domain(row)

    async def get_by_technical_identity(
        self, source_system: str, source_instance_id: str, native_id: str
    ) -> Node | None:
        stmt = select(NodeORM).where(
            NodeORM.source_system == source_system,
            NodeORM.source_instance_id == source_instance_id,
            NodeORM.native_id == native_id,
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return _to_domain(row) if row is not None else None

    async def get_by_technical_identity_any_instance(
        self, source_system: str, native_id: str
    ) -> Node | None:
        """Same lookup, ignoring source_instance_id — used by link
        extraction (synchronization/link_extraction.py), which resolves a
        target_ref to a source_system without necessarily knowing which
        connector instance produced it. There is exactly one instance per
        source in this project's current fixture world
        (docs/phases/PHASE-07.md); a true multi-instance directory is
        Phase 16's concern. Deterministic but not rigorously unique if
        that ever changes — takes the first match."""
        stmt = select(NodeORM).where(
            NodeORM.source_system == source_system, NodeORM.native_id == native_id
        )
        row = (await self._session.execute(stmt)).scalars().first()
        return _to_domain(row) if row is not None else None

    async def get_many(self, node_ids: list[UUID]) -> list[Node]:
        if not node_ids:
            return []
        stmt = select(NodeORM).where(NodeORM.id.in_(node_ids))
        rows = (await self._session.execute(stmt)).scalars().all()
        return [_to_domain(r) for r in rows]

    async def list_direct_children(self, parent_id: UUID) -> list[Node]:
        """Immediate children only (docs/UI.md "Catalog Explorer" Hierarchy
        tab) — unlike list_descendants (the whole subtree), this is what a
        node's own detail view shows as "children", one level down."""
        stmt = (
            select(NodeORM)
            .where(NodeORM.parent_id == parent_id, NodeORM.deleted_at.is_(None))
            .order_by(NodeORM.path)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [_to_domain(r) for r in rows]

    async def list_descendants(
        self, ancestor_path: str, *, include_self: bool = True
    ) -> list[Node]:
        """Everything under `ancestor_path` (docs/persistence.md "Query
        patterns": `WHERE path <@ :ancestor_path` on Postgres — see
        persistence/dialect_compat.py for the SQLite equivalent)."""
        dialect_name = self._session.get_bind().dialect.name
        stmt = select(NodeORM).where(path_contains(NodeORM.path, ancestor_path, dialect_name))
        rows = (await self._session.execute(stmt)).scalars().all()
        results = [_to_domain(r) for r in rows]
        if not include_self:
            results = [r for r in results if r.path != ancestor_path]
        return results

    async def list_ancestors_of_path(self, path: str) -> list[Node]:
        """All nodes whose path is a prefix of `path` (walking upward),
        including the node at `path` itself if one exists."""
        labels = path.split(".")
        prefixes = [".".join(labels[: i + 1]) for i in range(len(labels))]
        stmt = select(NodeORM).where(NodeORM.path.in_(prefixes))
        rows = (await self._session.execute(stmt)).scalars().all()
        by_path = {r.path: r for r in rows}
        return [_to_domain(by_path[p]) for p in prefixes if p in by_path]

    async def soft_delete(self, node_id: UUID, deleted_at: datetime) -> None:
        row = await self._session.get(NodeORM, node_id)
        if row is not None:
            row.deleted_at = deleted_at
            await self._session.flush()

    async def get_by_attribute(
        self, source_system: str, kind: str, attr_key: str, attr_value: str
    ) -> Node | None:
        """A node identified by an attribute value rather than its
        native_id — synchronization/link_extraction.py's CONFTITLE:
        resolution needs this to find a Confluence SPACE by its `key`
        attribute (Confluence's short space code, e.g. "TALENT" — distinct
        from the space's own numeric native_id) before it can look up a
        page by title within it. No source_instance_id param, same
        "any instance" limitation get_by_technical_identity_any_instance
        already documents — the caller here has no instance context to
        narrow by. `.as_string()` is SQLAlchemy's dialect-portable
        JSON-value accessor (verified against both Postgres and SQLite —
        see retrieval/query_compiler.py's identical use), so no dialect
        branch is needed here."""
        stmt = select(NodeORM).where(
            NodeORM.source_system == source_system,
            NodeORM.kind == kind,
            NodeORM.attributes[attr_key].as_string() == attr_value,
            NodeORM.deleted_at.is_(None),
        )
        row = (await self._session.execute(stmt)).scalars().first()
        return _to_domain(row) if row is not None else None

    async def find_by_name_under(self, ancestor_path: str, kind: str, name: str) -> Node | None:
        """A node by exact name, anywhere under `ancestor_path` — the
        other half of link_extraction.py's CONFTITLE: resolution: once the
        owning SPACE is found (get_by_attribute above), the referenced
        PAGE is looked up by title within that space's whole subtree
        (nested pages aren't direct children of the space, so a plain
        list_direct_children wouldn't find them). Confluence page titles
        are unique within a space, so an exact match is safe here — this
        is not a fuzzy or partial-match lookup."""
        dialect_name = self._session.get_bind().dialect.name
        stmt = select(NodeORM).where(
            path_contains(NodeORM.path, ancestor_path, dialect_name),
            NodeORM.kind == kind,
            NodeORM.name == name,
            NodeORM.deleted_at.is_(None),
        )
        row = (await self._session.execute(stmt)).scalars().first()
        return _to_domain(row) if row is not None else None

    async def list_active_native_ids(
        self, source_system: str, source_instance_id: str
    ) -> list[tuple[UUID, str, str]]:
        """(id, native_id, kind) for every active node from one connector
        instance — synchronization/orchestrator.py's generalized tombstone
        sweep diffs this against the native_ids actually walked this sync
        pass; whatever's missing no longer exists upstream. Deliberately
        just the three columns needed for that diff, not full Node rows —
        this can be every node a large connector instance has ever synced."""
        stmt = select(NodeORM.id, NodeORM.native_id, NodeORM.kind).where(
            NodeORM.source_system == source_system,
            NodeORM.source_instance_id == source_instance_id,
            NodeORM.deleted_at.is_(None),
        )
        rows = (await self._session.execute(stmt)).all()
        return [(r.id, r.native_id, r.kind) for r in rows]
