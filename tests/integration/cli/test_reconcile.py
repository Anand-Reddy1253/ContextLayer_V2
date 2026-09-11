"""catalog.reconcile_context_space's resolved/unresolved reporting
(docs/phases/PHASE-08.md), using the real talentflow-identity.yaml
fixture and exercised through the same functions cli/main.py's
`reconcile` command calls (not a subprocess — faster, same code path).
"""

from context_fabric.catalog import (
    create_context_space,
    find_context_space_config_by_id,
    load_business_tree_config,
    load_context_space_config,
    reconcile_context_space,
    seed_business_tree,
)
from context_fabric.connectors.azure_devops.fixture import AzureDevOpsFixtureConnector
from context_fabric.connectors.github.fixture import GitHubFixtureConnector
from context_fabric.persistence.repositories.context_space import ContextSpaceRepository
from context_fabric.persistence.repositories.node import NodeRepository
from context_fabric.synchronization import sync_source


async def _create_talentflow_identity(db_session):
    node_repo = NodeRepository(db_session)
    context_space_repo = ContextSpaceRepository(db_session)
    await seed_business_tree(node_repo, load_business_tree_config())
    config = load_context_space_config(find_context_space_config_by_id("talentflow/identity"))  # type: ignore[arg-type]
    space = await create_context_space(context_space_repo, node_repo, config)
    return node_repo, space


async def test_reconcile_before_any_sync_reports_all_unresolved(db_session):
    node_repo, space = await _create_talentflow_identity(db_session)

    report = await reconcile_context_space(node_repo, space)

    assert len(report.results) == 4
    assert report.all_resolved is False
    assert all(not r.resolved for r in report.results)


async def test_reconcile_with_only_ado_synced_reports_partial(db_session):
    node_repo, space = await _create_talentflow_identity(db_session)
    await sync_source(db_session, AzureDevOpsFixtureConnector(), source_instance_id="ado-acme")

    report = await reconcile_context_space(node_repo, space)

    by_capability = {r.binding.capability.value: r.resolved for r in report.results}
    assert by_capability["WORK_MANAGEMENT"] is True
    assert by_capability["CODE"] is False  # GitHub not synced yet
    assert by_capability["DOCUMENTATION"] is False  # confluence never implemented
    assert report.all_resolved is False


async def test_reconcile_after_both_synced_resolves_everything_but_confluence(db_session):
    node_repo, space = await _create_talentflow_identity(db_session)
    await sync_source(db_session, AzureDevOpsFixtureConnector(), source_instance_id="ado-acme")
    await sync_source(db_session, GitHubFixtureConnector(), source_instance_id="github-acme")

    report = await reconcile_context_space(node_repo, space)

    resolved_by_capability = {r.binding.capability.value: r.resolved for r in report.results}
    assert resolved_by_capability["CODE"] is True
    assert resolved_by_capability["WORK_MANAGEMENT"] is True
    # Confluence is explicitly out of scope (AGENTS.md §4) — this binding
    # can never resolve, and that must be reported clearly, not crash.
    assert resolved_by_capability["DOCUMENTATION"] is False

    resolved_count = sum(1 for r in report.results if r.resolved)
    assert resolved_count == 3
