"""api/routes/catalog.py's get_node_graph: the ltree ancestor-chain walk
and the separate BINDS/HAS_CONTEXT_SPACE business-context walk
(_bound_business_chain), added after a real user report — a leaf
technical node's (a PR's) "full graph" showed almost nothing, never its
containing Project/Repository, and never the team or org it's bound to.

native_id/source_instance_id values here are deliberately distinctive
(same convention as test_scope_resolution.py) since this shared dev
database also holds real data from live-connector smoke testing.
"""

from __future__ import annotations

from datetime import UTC, datetime

from context_fabric.api.routes.catalog import get_node_graph
from context_fabric.catalog import (
    add_binding,
    create_business_node,
    create_context_space_from_fields,
)
from context_fabric.domain.enums import Capability, Layer
from context_fabric.domain.node import Node
from context_fabric.persistence.repositories.context_space import ContextSpaceRepository
from context_fabric.persistence.repositories.node import NodeRepository

_INSTANCE = "ado-bmw-test"


async def _make_technical_chain(node_repo: NodeRepository, now):  # type: ignore[no-untyped-def]
    """Project -> Repository -> PullRequest, all technical, connected only
    by path (no real CONTAINS edges — matches how connectors actually
    write these)."""
    project = await node_repo.create(
        Node(
            layer=Layer.TECHNICAL,
            kind="PROJECT",
            name="BMW Test Project",
            path="ado_bmw_test.project",
            source_system="azure_devops",
            source_instance_id=_INSTANCE,
            native_id="bmw-test-project",
            first_seen_at=now,
            last_seen_at=now,
            created_at=now,
            updated_at=now,
        )
    )
    repo = await node_repo.create(
        Node(
            layer=Layer.TECHNICAL,
            kind="REPOSITORY",
            name="bmw-test-repo",
            path="ado_bmw_test.project.repo",
            source_system="azure_devops",
            source_instance_id=_INSTANCE,
            native_id="bmw-test-project/bmw-test-repo",
            first_seen_at=now,
            last_seen_at=now,
            created_at=now,
            updated_at=now,
        )
    )
    pr = await node_repo.create(
        Node(
            layer=Layer.TECHNICAL,
            kind="PULL_REQUEST",
            name="Add favourite toggle",
            path="ado_bmw_test.project.repo.pr_1",
            source_system="azure_devops",
            source_instance_id=_INSTANCE,
            native_id="bmw-test-project/bmw-test-repo/pullrequest/1",
            first_seen_at=now,
            last_seen_at=now,
            created_at=now,
            updated_at=now,
        )
    )
    return project, repo, pr


async def test_leaf_node_graph_includes_its_ltree_ancestor_chain(db_session):
    node_repo = NodeRepository(db_session)
    now = datetime.now(UTC)
    project, repo, pr = await _make_technical_chain(node_repo, now)

    result = await get_node_graph(pr.id, session=db_session)

    node_ids = {n["id"] for n in result["nodes"]}
    assert str(pr.id) in node_ids
    assert str(repo.id) in node_ids
    assert str(project.id) in node_ids


async def test_leaf_node_graph_includes_bound_team_and_org(db_session):
    node_repo = NodeRepository(db_session)
    context_space_repo = ContextSpaceRepository(db_session)
    now = datetime.now(UTC)
    _, repo, pr = await _make_technical_chain(node_repo, now)

    org = await create_business_node(node_repo, parent_id=None, kind="ORG", name="BMW Test Org")
    team = await create_business_node(
        node_repo, parent_id=org.id, kind="TEAM", name="BMW Test Team"
    )
    space = await create_context_space_from_fields(
        context_space_repo,
        id="bmw-test-space",
        name="BMW Test Space",
        description="",
        business_node_id=team.id,
    )
    await add_binding(
        context_space_repo,
        space.id,
        capability=Capability.CODE,
        source_system="azure_devops",
        source_instance_id=_INSTANCE,
        native_container=repo.native_id,
    )

    result = await get_node_graph(pr.id, session=db_session)

    node_ids = {n["id"] for n in result["nodes"]}
    assert str(team.id) in node_ids
    assert str(org.id) in node_ids

    edge_types_by_pair = {(e["src_id"], e["dst_id"]): e["type"] for e in result["edges"]}
    assert edge_types_by_pair.get((f"ctxspace:{space.id}", str(repo.id))) == "BINDS"
    assert edge_types_by_pair.get((str(team.id), f"ctxspace:{space.id}")) == "HAS_CONTEXT_SPACE"
    assert edge_types_by_pair.get((str(org.id), str(team.id))) == "CONTAINS"


async def test_node_with_no_binding_gets_no_business_nodes(db_session):
    node_repo = NodeRepository(db_session)
    now = datetime.now(UTC)
    _, _, pr = await _make_technical_chain(node_repo, now)

    result = await get_node_graph(pr.id, session=db_session)

    assert not any(n["kind"] == "CONTEXT_SPACE" for n in result["nodes"])
