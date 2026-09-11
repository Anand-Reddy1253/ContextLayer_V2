"""The permanent idempotency gate (docs/phases/PHASE-06.md,
AGENTS.md §3): running sync twice against unchanged fixture data produces
zero net graph change on the second run. This test must stay green
through every later phase.
"""

import pytest

from context_fabric.connectors.azure_devops.fixture import AzureDevOpsFixtureConnector
from context_fabric.connectors.github.fixture import GitHubFixtureConnector
from context_fabric.persistence.repositories.sync_run import SyncRunRepository
from context_fabric.synchronization import sync_source


@pytest.mark.parametrize(
    ("connector_cls", "source_instance_id"),
    [
        (AzureDevOpsFixtureConnector, "ado-acme"),
        (GitHubFixtureConnector, "github-acme"),
    ],
    ids=["azure_devops", "github"],
)
async def test_sync_twice_produces_zero_net_change_on_second_run(
    db_session, connector_cls, source_instance_id
):
    connector = connector_cls()

    first = await sync_source(db_session, connector, source_instance_id=source_instance_id)
    assert first.status.value == "SUCCEEDED"
    assert first.nodes_upserted > 0
    assert first.edges_created > 0

    second = await sync_source(db_session, connector, source_instance_id=source_instance_id)
    assert second.status.value == "SUCCEEDED"
    assert second.nodes_upserted == 0
    assert second.edges_created == 0
    assert second.nodes_tombstoned == 0


async def test_sync_run_history_records_both_runs(db_session):
    # Uses a scope_id no other test or manual run touches, so this
    # doesn't depend on (or get confused by) unrelated sync_run history
    # already sitting in a shared dev database.
    connector = AzureDevOpsFixtureConnector()
    scope_id = "ado-acme-history-test"
    first = await sync_source(db_session, connector, source_instance_id=scope_id)
    second = await sync_source(db_session, connector, source_instance_id=scope_id)

    runs = await SyncRunRepository(db_session).list_for_scope("azure_devops", scope_id)
    assert len(runs) == 2
    assert all(r.status.value == "SUCCEEDED" for r in runs)
    # Most recent first (list_for_scope orders by started_at desc).
    assert runs[0].id == second.id
    assert runs[0].nodes_upserted == 0
    assert runs[1].id == first.id
    assert runs[1].nodes_upserted > 0
