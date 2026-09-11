"""Ancestor/descendant queries over Node.path (ltree), the query pattern
docs/persistence.md documents as the core of scope resolution
(docs/RETRIEVAL.md).

Hand-built tree:

    acme
    acme.engineering
    acme.engineering.talentflow
    acme.engineering.talentflow.identity      (Identity Squad)
    acme.engineering.talentflow.identity.svc1 (identity-service, TECHNICAL)
    acme.engineering.payments                 (sibling branch)
"""

from context_fabric.domain.enums import Layer
from context_fabric.persistence.repositories.node import NodeRepository
from tests.integration.persistence.factories import make_node


async def _build_tree(node_repo: NodeRepository, now):  # type: ignore[no-untyped-def]
    acme = await node_repo.create(make_node(now, kind="ORG", path="acme"))
    eng = await node_repo.create(
        make_node(now, kind="DIVISION", path="acme.engineering", parent_id=acme.id)
    )
    talentflow = await node_repo.create(
        make_node(
            now, kind="TRIBE", path="acme.engineering.talentflow", parent_id=eng.id
        )
    )
    identity = await node_repo.create(
        make_node(
            now,
            kind="SQUAD",
            path="acme.engineering.talentflow.identity",
            parent_id=talentflow.id,
        )
    )
    svc = await node_repo.create(
        make_node(
            now,
            layer=Layer.TECHNICAL,
            kind="REPOSITORY",
            name="identity-service",
            path="acme.engineering.talentflow.identity.svc1",
            parent_id=identity.id,
            source_system="github",
            source_instance_id="github-acme",
            native_id="acme-org/identity-service",
        )
    )
    payments = await node_repo.create(
        make_node(now, kind="TRIBE", path="acme.engineering.payments", parent_id=eng.id)
    )
    return acme, eng, talentflow, identity, svc, payments


async def test_list_descendants_includes_self_and_children_only(db_session, now):
    node_repo = NodeRepository(db_session)
    acme, eng, talentflow, identity, svc, payments = await _build_tree(node_repo, now)

    descendants = await node_repo.list_descendants("acme.engineering.talentflow")
    ids = {n.id for n in descendants}

    assert talentflow.id in ids  # includes self
    assert identity.id in ids
    assert svc.id in ids
    assert eng.id not in ids  # ancestor, not descendant
    assert payments.id not in ids  # sibling branch, not under talentflow


async def test_list_descendants_exclude_self(db_session, now):
    node_repo = NodeRepository(db_session)
    _, _, talentflow, identity, svc, _ = await _build_tree(node_repo, now)

    descendants = await node_repo.list_descendants(
        "acme.engineering.talentflow", include_self=False
    )
    ids = {n.id for n in descendants}
    assert talentflow.id not in ids
    assert identity.id in ids
    assert svc.id in ids


async def test_list_ancestors_of_path_walks_upward(db_session, now):
    node_repo = NodeRepository(db_session)
    acme, eng, talentflow, identity, svc, _ = await _build_tree(node_repo, now)

    ancestors = await node_repo.list_ancestors_of_path(
        "acme.engineering.talentflow.identity.svc1"
    )
    assert [n.id for n in ancestors] == [acme.id, eng.id, talentflow.id, identity.id, svc.id]
