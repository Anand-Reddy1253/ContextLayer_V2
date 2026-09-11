"""Link extraction (docs/phases/PHASE-07.md): get_links() output becomes
PROPOSED MENTIONS/RELATED_TO edges, including across connectors.
"""

from context_fabric.connectors.azure_devops.fixture import AzureDevOpsFixtureConnector
from context_fabric.connectors.github.fixture import GitHubFixtureConnector
from context_fabric.domain.enums import EdgeOrigin, EdgeState, EdgeType
from context_fabric.persistence.repositories.edge import EdgeRepository
from context_fabric.persistence.repositories.node import NodeRepository
from context_fabric.synchronization import sync_source


async def test_cross_connector_mention_edge_exists_after_syncing_both(db_session):
    # A GitHub commit's message mentions AB#312 — an Azure DevOps work
    # item. This is the cross-connector link Phase 7 exists to prove.
    await sync_source(db_session, AzureDevOpsFixtureConnector(), source_instance_id="ado-acme")
    await sync_source(db_session, GitHubFixtureConnector(), source_instance_id="github-acme")

    node_repo = NodeRepository(db_session)
    edge_repo = EdgeRepository(db_session)

    commit_node = await node_repo.get_by_technical_identity(
        "github", "github-acme", "acme-org/identity-service@abc1234"
    )
    story_node = await node_repo.get_by_technical_identity("azure_devops", "ado-acme", "312")
    assert commit_node is not None
    assert story_node is not None

    edges = await edge_repo.list_from(commit_node.id)
    mention_edges = [e for e in edges if e.dst_id == story_node.id]
    assert len(mention_edges) == 1
    edge = mention_edges[0]
    assert edge.type is EdgeType.MENTIONS
    assert edge.origin is EdgeOrigin.SYNC_EXTRACTED
    assert edge.state is EdgeState.PROPOSED


async def test_unresolvable_target_is_logged_not_a_hard_failure(db_session):
    # Story 312's ArtifactLink relation points at ADO's own PR-42 — but
    # PRs are deliberately not part of ADO's list_children walk
    # (connectors/azure_devops/fixture.py, matching real Azure Boards'
    # own work-item/area-path hierarchy), so PR-42 is never synced as a
    # node. Resolution correctly fails, and per docs/CONNECTORS.md that's
    # logged and skipped — not a raised exception, not a broken sync run.
    run = await sync_source(
        db_session, AzureDevOpsFixtureConnector(), source_instance_id="ado-acme"
    )
    assert run.status.value == "SUCCEEDED"

    node_repo = NodeRepository(db_session)
    story_node = await node_repo.get_by_technical_identity("azure_devops", "ado-acme", "312")
    assert story_node is not None
    # PR-42 genuinely doesn't exist as a node — confirms the premise.
    assert (
        await node_repo.get_by_technical_identity("azure_devops", "ado-acme", "PR-42")
    ) is None


async def test_extracted_edges_are_never_active(db_session):
    await sync_source(db_session, AzureDevOpsFixtureConnector(), source_instance_id="ado-acme")

    edge_repo = EdgeRepository(db_session)
    node_repo = NodeRepository(db_session)
    story_node = await node_repo.get_by_technical_identity("azure_devops", "ado-acme", "312")

    edges = await edge_repo.list_from(story_node.id)
    extracted = [e for e in edges if e.origin is EdgeOrigin.SYNC_EXTRACTED]
    assert extracted  # story 312's description mentions AB#301 (epic 301)
    assert all(e.state is EdgeState.PROPOSED for e in extracted)


async def test_resync_does_not_duplicate_extracted_edges(db_session):
    connector = AzureDevOpsFixtureConnector()
    node_repo = NodeRepository(db_session)
    edge_repo = EdgeRepository(db_session)

    await sync_source(db_session, connector, source_instance_id="ado-acme")
    story_node = await node_repo.get_by_technical_identity("azure_devops", "ado-acme", "312")
    first_run_edges = len(await edge_repo.list_from(story_node.id))

    await sync_source(db_session, connector, source_instance_id="ado-acme")
    second_run_edges = len(await edge_repo.list_from(story_node.id))

    assert first_run_edges == second_run_edges
    assert first_run_edges > 0
