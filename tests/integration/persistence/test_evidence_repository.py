from context_fabric.domain.evidence import Evidence
from context_fabric.persistence.repositories.evidence import EvidenceRepository
from context_fabric.persistence.repositories.node import NodeRepository
from tests.integration.persistence.factories import make_evidence, make_technical_node


async def test_create_and_get_round_trips_all_fields(db_session, now):
    node_repo = NodeRepository(db_session)
    evidence_repo = EvidenceRepository(db_session)
    node = await node_repo.create(make_technical_node(now))

    evidence = make_evidence(
        now,
        node.id,
        source_version="rev-4",
        content_hash="hash-1",
        acl_ref={"group": "identity-squad"},
    )
    created = await evidence_repo.create(evidence)
    assert isinstance(created, Evidence)

    fetched = await evidence_repo.get(created.id)
    assert fetched == created
    assert fetched.source_version == "rev-4"
    assert fetched.acl_ref == {"group": "identity-squad"}


async def test_list_for_node(db_session, now):
    node_repo = NodeRepository(db_session)
    evidence_repo = EvidenceRepository(db_session)
    node = await node_repo.create(make_technical_node(now))
    other = await node_repo.create(
        make_technical_node(now, path="github.other", native_id="org/other")
    )

    e1 = await evidence_repo.create(make_evidence(now, node.id))
    await evidence_repo.create(make_evidence(now, other.id))

    results = await evidence_repo.list_for_node(node.id)
    assert [r.id for r in results] == [e1.id]
