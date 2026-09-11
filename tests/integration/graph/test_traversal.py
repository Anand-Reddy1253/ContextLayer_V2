"""Bounded graph traversal (docs/phases/PHASE-07.md) — hand-built graph,
deterministic hop counts and edge-type filters, not just real sync data.

Graph:

    a --CONTAINS--> b --CONTAINS--> c --CONTAINS--> d
    a --DEPENDS_ON--> e
    b --MENTIONS--> f
"""

from context_fabric.domain.edge import Edge
from context_fabric.domain.enums import EdgeOrigin, EdgeType, Layer
from context_fabric.domain.node import Node
from context_fabric.graph.traversal import traverse
from context_fabric.persistence.repositories.edge import EdgeRepository
from context_fabric.persistence.repositories.node import NodeRepository


async def _make_node(node_repo: NodeRepository, now, label: str) -> Node:
    node = Node(
        layer=Layer.TECHNICAL,
        kind="ITEM",
        name=label,
        path=label,
        source_system="fake_graph_source",
        source_instance_id="fake-1",
        native_id=label,
        first_seen_at=now,
        last_seen_at=now,
        created_at=now,
        updated_at=now,
    )
    return await node_repo.create(node)


async def _make_edge(
    edge_repo: EdgeRepository, now, src: Node, dst: Node, edge_type: EdgeType
) -> Edge:
    edge = Edge(
        src_id=src.id,
        dst_id=dst.id,
        type=edge_type,
        origin=EdgeOrigin.SYNC_STRUCTURAL,
        first_seen_at=now,
        last_seen_at=now,
    )
    return await edge_repo.create(edge)


async def _build_graph(db_session, now):
    node_repo = NodeRepository(db_session)
    edge_repo = EdgeRepository(db_session)

    a = await _make_node(node_repo, now, "a")
    b = await _make_node(node_repo, now, "b")
    c = await _make_node(node_repo, now, "c")
    d = await _make_node(node_repo, now, "d")
    e = await _make_node(node_repo, now, "e")
    f = await _make_node(node_repo, now, "f")

    await _make_edge(edge_repo, now, a, b, EdgeType.CONTAINS)
    await _make_edge(edge_repo, now, b, c, EdgeType.CONTAINS)
    await _make_edge(edge_repo, now, c, d, EdgeType.CONTAINS)
    await _make_edge(edge_repo, now, a, e, EdgeType.DEPENDS_ON)
    await _make_edge(edge_repo, now, b, f, EdgeType.MENTIONS)

    return a, b, c, d, e, f


async def test_traverse_respects_max_hops(db_session, now):
    a, b, c, d, e, f = await _build_graph(db_session, now)

    one_hop = await traverse(db_session, a.id, max_hops=1)
    assert {n.id for n in one_hop} == {b.id, e.id}

    two_hop = await traverse(db_session, a.id, max_hops=2)
    assert {n.id for n in two_hop} == {b.id, e.id, c.id, f.id}

    three_hop = await traverse(db_session, a.id, max_hops=3)
    assert {n.id for n in three_hop} == {b.id, e.id, c.id, f.id, d.id}


async def test_traverse_filters_by_edge_type(db_session, now):
    a, b, c, d, e, f = await _build_graph(db_session, now)

    contains_only = await traverse(db_session, a.id, max_hops=3, edge_types=[EdgeType.CONTAINS])
    assert {n.id for n in contains_only} == {b.id, c.id, d.id}

    depends_only = await traverse(db_session, a.id, max_hops=3, edge_types=[EdgeType.DEPENDS_ON])
    assert {n.id for n in depends_only} == {e.id}


async def test_traverse_direction_in(db_session, now):
    a, b, c, d, e, f = await _build_graph(db_session, now)

    reachable_into_d = await traverse(db_session, d.id, max_hops=3, direction="in")
    assert {n.id for n in reachable_into_d} == {c.id, b.id, a.id}


async def test_traverse_direction_both(db_session, now):
    a, b, c, d, e, f = await _build_graph(db_session, now)

    both = await traverse(db_session, b.id, max_hops=1, direction="both")
    assert {n.id for n in both} == {c.id, f.id, a.id}


async def test_traverse_excludes_root_by_default(db_session, now):
    a, b, c, d, e, f = await _build_graph(db_session, now)
    result = await traverse(db_session, a.id, max_hops=1)
    assert a.id not in {n.id for n in result}


async def test_traverse_include_root(db_session, now):
    a, b, c, d, e, f = await _build_graph(db_session, now)
    result = await traverse(db_session, a.id, max_hops=1, include_root=True)
    assert a.id in {n.id for n in result}


async def test_traverse_no_matching_edges_returns_empty(db_session, now):
    a, b, c, d, e, f = await _build_graph(db_session, now)
    result = await traverse(db_session, d.id, max_hops=3, direction="out")
    assert result == []
