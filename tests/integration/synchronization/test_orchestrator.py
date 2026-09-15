"""synchronization/orchestrator.py — docs/phases/PHASE-06.md's other two
test requirements beyond idempotency (covered separately in
tests/acceptance/test_sync_is_idempotent.py): pagination followed to
completion, and tombstones soft-deleting (not hard-deleting) an existing
node.

Uses a small purpose-built fake connector rather than the real ADO/GitHub
fixtures, so the pagination boundary and the tombstone-of-an-existing-node
scenario are both under direct, deterministic control.
"""

from __future__ import annotations

from context_fabric.domain.connector_types import (
    ACLReference,
    ChangePage,
    Page,
    SourceContainer,
    SourceContent,
    SourceLink,
    SourceObject,
)
from context_fabric.domain.errors import NotFound
from context_fabric.persistence.repositories.edge import EdgeRepository
from context_fabric.persistence.repositories.node import NodeRepository
from context_fabric.synchronization import sync_source
from context_fabric.synchronization.orchestrator import SyncStats, _sweep_stale

_PAGE_SIZE = 2


class _FakeConnector:
    """`deleted_ids` models a source-state snapshot: a real deletion
    means an object disappears from list_children *and* shows up in
    get_changes — never both-present-and-deleted at once (that would be
    self-contradictory and isn't how any real connector behaves)."""

    source_system = "fake_sync_source"
    mode = "fixture"

    def __init__(self, deleted_ids: frozenset[str] = frozenset()) -> None:
        self._deleted_ids = deleted_ids
        self._children = [
            SourceObject(native_id=f"child-{i}", kind="ITEM", name=f"Item {i}")
            for i in range(5)
            if f"child-{i}" not in deleted_ids
        ]

    async def discover_containers(self) -> list[SourceContainer]:
        return [SourceContainer(id="root", name="Root", kind="ROOT", native_id="root")]

    async def list_children(self, parent_id: str, cursor: str | None = None) -> Page[SourceObject]:
        if parent_id != "root":
            return Page(items=[], next_cursor=None)
        start = int(cursor) if cursor else 0
        end = start + _PAGE_SIZE
        next_cursor = str(end) if end < len(self._children) else None
        return Page(items=self._children[start:end], next_cursor=next_cursor)

    async def get_object(self, native_id: str) -> SourceObject:
        raise NotFound("not needed for this test", source_system=self.source_system)

    async def get_content(self, native_id: str, version: str | None = None) -> SourceContent:
        raise NotFound("not needed for this test", source_system=self.source_system)

    async def get_changes(self, cursor: str | None = None) -> ChangePage:
        if cursor is not None:
            return ChangePage(items=[], next_cursor=None, has_more=False)
        items = [
            SourceObject(native_id=nid, kind="ITEM", name="", deleted=True)
            for nid in self._deleted_ids
        ]
        return ChangePage(items=items, next_cursor=None, has_more=False)

    async def get_links(self, native_id: str) -> list[SourceLink]:
        return []

    async def get_acl_reference(self, native_id: str) -> ACLReference:
        raise NotFound("not needed for this test", source_system=self.source_system)


async def test_pagination_is_followed_to_completion(db_session):
    connector = _FakeConnector()
    run = await sync_source(db_session, connector, source_instance_id="fake-instance")

    assert run.nodes_upserted == 6  # 1 root + 5 children across 3 pages
    assert run.edges_created == 5  # one CONTAINS edge per child

    node_repo = NodeRepository(db_session)
    for i in range(5):
        node = await node_repo.get_by_technical_identity(
            "fake_sync_source", "fake-instance", f"child-{i}"
        )
        assert node is not None
        assert node.name == f"Item {i}"


async def test_tombstone_soft_deletes_not_hard_deletes(db_session):
    # First sync: the source state has child-2 present, nothing deleted.
    connector_before = _FakeConnector()
    await sync_source(db_session, connector_before, source_instance_id="fake-instance")

    node_repo = NodeRepository(db_session)
    node = await node_repo.get_by_technical_identity(
        "fake_sync_source", "fake-instance", "child-2"
    )
    assert node is not None
    assert node.deleted_at is None

    # Second sync: the source state has since changed — child-2 is gone
    # from the hierarchy and reported deleted via get_changes.
    connector_after = _FakeConnector(deleted_ids=frozenset({"child-2"}))
    run = await sync_source(db_session, connector_after, source_instance_id="fake-instance")
    assert run.nodes_tombstoned == 1

    tombstoned = await node_repo.get_by_technical_identity(
        "fake_sync_source", "fake-instance", "child-2"
    )
    # Soft delete: the row still exists and is still gettable by identity —
    # a hard delete would make this None instead.
    assert tombstoned is not None
    assert tombstoned.id == node.id
    assert tombstoned.deleted_at is not None

    # Running the "after" state again must not re-tombstone an
    # already-deleted node — idempotency applies to the sweep too.
    second_run = await sync_source(db_session, connector_after, source_instance_id="fake-instance")
    assert second_run.nodes_tombstoned == 0


async def test_sweep_stale_refuses_to_run_against_a_partial_walk(db_session):
    """The guard this exists for: an incremental ("changed since X") sync
    pass would only populate a subset of `expanded`. If `_sweep_stale` ever
    ran against that partial set, every node the delta didn't happen to
    touch would look deleted, and every edge touching it would cascade
    away. This proves the sweep is a no-op unless `walk_complete` was
    genuinely reached — not just that today's callers happen to behave."""
    connector = _FakeConnector()
    await sync_source(db_session, connector, source_instance_id="fake-instance")

    node_repo = NodeRepository(db_session)
    edge_repo = EdgeRepository(db_session)
    child = await node_repo.get_by_technical_identity(
        "fake_sync_source", "fake-instance", "child-2"
    )
    assert child is not None and child.deleted_at is None

    # Simulate a partial/incremental pass: `expanded` deliberately omits
    # every node that actually still exists, exactly what a "changed since
    # X" delta would look like when nothing changed. walk_complete is left
    # at its default False.
    partial_stats = SyncStats(expanded=set())
    assert partial_stats.walk_complete is False

    await _sweep_stale(node_repo, edge_repo, connector, "fake-instance", partial_stats)

    assert partial_stats.nodes_tombstoned == 0
    untouched = await node_repo.get_by_technical_identity(
        "fake_sync_source", "fake-instance", "child-2"
    )
    assert untouched.deleted_at is None, (
        "a partial walk must never tombstone nodes it simply didn't visit"
    )


async def test_structural_edges_created_between_parent_and_children(db_session):
    connector = _FakeConnector()
    await sync_source(db_session, connector, source_instance_id="fake-instance")

    node_repo = NodeRepository(db_session)
    edge_repo = EdgeRepository(db_session)

    root = await node_repo.get_by_technical_identity("fake_sync_source", "fake-instance", "root")
    edges = await edge_repo.list_from(root.id)
    assert len(edges) == 5
    assert all(e.type.value == "CONTAINS" for e in edges)
    assert all(e.origin.value == "SYNC_STRUCTURAL" for e in edges)
