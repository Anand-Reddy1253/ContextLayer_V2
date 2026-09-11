import pytest
from sqlalchemy.exc import IntegrityError

from context_fabric.domain.edge import Edge
from context_fabric.domain.enums import EdgeOrigin, EdgeState, EdgeType
from context_fabric.persistence.repositories.edge import EdgeRepository
from context_fabric.persistence.repositories.node import NodeRepository
from tests.integration.persistence.factories import make_edge, make_technical_node


async def test_create_and_get_round_trips_all_fields(db_session, now):
    node_repo = NodeRepository(db_session)
    edge_repo = EdgeRepository(db_session)
    src = await node_repo.create(make_technical_node(now, path="github.a", native_id="org/a"))
    dst = await node_repo.create(make_technical_node(now, path="github.b", native_id="org/b"))

    edge = make_edge(
        now,
        src.id,
        dst.id,
        type=EdgeType.MENTIONS,
        origin=EdgeOrigin.SYNC_EXTRACTED,
        state=EdgeState.PROPOSED,
        confidence=0.7,
        attributes={"snippet": "see AB#312"},
    )
    created = await edge_repo.create(edge)
    assert isinstance(created, Edge)

    fetched = await edge_repo.get(created.id)
    assert fetched is not None
    assert fetched == created
    assert fetched.state is EdgeState.PROPOSED
    assert fetched.confidence == 0.7
    assert fetched.attributes == {"snippet": "see AB#312"}


async def test_edge_identity_uniqueness_enforced(db_session, now):
    node_repo = NodeRepository(db_session)
    edge_repo = EdgeRepository(db_session)
    src = await node_repo.create(make_technical_node(now, path="github.a", native_id="org/a"))
    dst = await node_repo.create(make_technical_node(now, path="github.b", native_id="org/b"))

    await edge_repo.create(make_edge(now, src.id, dst.id))
    with pytest.raises(IntegrityError):
        await edge_repo.create(make_edge(now, src.id, dst.id))


async def test_same_pair_different_origin_is_not_a_duplicate(db_session, now):
    # ux_edge_identity is (src_id, dst_id, type, origin) — a SYNC_STRUCTURAL
    # CONTAINS edge and a HUMAN-drawn CONTAINS edge between the same two
    # nodes are legitimately distinct rows.
    node_repo = NodeRepository(db_session)
    edge_repo = EdgeRepository(db_session)
    src = await node_repo.create(make_technical_node(now, path="github.a", native_id="org/a"))
    dst = await node_repo.create(make_technical_node(now, path="github.b", native_id="org/b"))

    await edge_repo.create(make_edge(now, src.id, dst.id, origin=EdgeOrigin.SYNC_STRUCTURAL))
    second = await edge_repo.create(make_edge(now, src.id, dst.id, origin=EdgeOrigin.HUMAN))
    assert second is not None


async def test_list_from_excludes_deleted_by_default(db_session, now):
    node_repo = NodeRepository(db_session)
    edge_repo = EdgeRepository(db_session)
    src = await node_repo.create(make_technical_node(now, path="github.a", native_id="org/a"))
    dst = await node_repo.create(make_technical_node(now, path="github.b", native_id="org/b"))

    live = await edge_repo.create(make_edge(now, src.id, dst.id, type=EdgeType.MENTIONS))
    await edge_repo.create(
        make_edge(now, src.id, dst.id, type=EdgeType.RELATED_TO, deleted_at=now)
    )

    edges = await edge_repo.list_from(src.id)
    ids = {e.id for e in edges}
    assert live.id in ids
    assert len(edges) == 1
