"""synchronization/state.py — sync_state.cursor persistence, independent
of any connector's fixture data (docs/phases/PHASE-06.md "sync_state.cursor
advances correctly"). The fixture connectors always fully drain
get_changes in one sync_source() call (Phase 6 has no true incremental
resume), so the mechanism is proven directly here with an explicit
cursor value rather than derived from fixture pagination that wouldn't
demonstrate anything beyond "ends at None."
"""

from context_fabric.domain.errors import Transient
from context_fabric.persistence.repositories.sync_run import SyncRunRepository
from context_fabric.persistence.repositories.sync_state import SyncStateRepository
from context_fabric.synchronization import state


async def test_start_run_creates_running_sync_run_and_sync_state(db_session):
    sync_run_repo = SyncRunRepository(db_session)
    sync_state_repo = SyncStateRepository(db_session)

    run = await state.start_run(
        sync_run_repo,
        sync_state_repo,
        source_system="azure_devops",
        scope_id="ado-acme",
        correlation_id="corr-1",
    )
    assert run.status.value == "RUNNING"

    saved_state = await sync_state_repo.get("azure_devops", "ado-acme")
    assert saved_state.status.value == "RUNNING"


async def test_finish_run_success_persists_cursor(db_session):
    sync_run_repo = SyncRunRepository(db_session)
    sync_state_repo = SyncStateRepository(db_session)

    run = await state.start_run(
        sync_run_repo,
        sync_state_repo,
        source_system="azure_devops",
        scope_id="ado-acme",
        correlation_id="corr-2",
    )
    await state.finish_run_success(
        sync_run_repo,
        sync_state_repo,
        run,
        nodes_upserted=5,
        nodes_tombstoned=1,
        edges_created=4,
        cursor="42",
    )

    saved_state = await sync_state_repo.get("azure_devops", "ado-acme")
    assert saved_state.cursor == "42"
    assert saved_state.status.value == "SUCCEEDED"
    assert saved_state.last_successful_sync is not None

    saved_run = await sync_run_repo.get(run.id)
    assert saved_run.status.value == "SUCCEEDED"
    assert saved_run.nodes_upserted == 5
    assert saved_run.nodes_tombstoned == 1
    assert saved_run.edges_created == 4


async def test_cursor_advances_across_successive_runs(db_session):
    sync_run_repo = SyncRunRepository(db_session)
    sync_state_repo = SyncStateRepository(db_session)

    run1 = await state.start_run(
        sync_run_repo, sync_state_repo,
        source_system="github", scope_id="github-acme", correlation_id="c1",
    )
    await state.finish_run_success(
        sync_run_repo, sync_state_repo, run1,
        nodes_upserted=1, nodes_tombstoned=0, edges_created=1, cursor="10",
    )
    assert (await sync_state_repo.get("github", "github-acme")).cursor == "10"

    run2 = await state.start_run(
        sync_run_repo, sync_state_repo,
        source_system="github", scope_id="github-acme", correlation_id="c2",
    )
    await state.finish_run_success(
        sync_run_repo, sync_state_repo, run2,
        nodes_upserted=0, nodes_tombstoned=0, edges_created=0, cursor="20",
    )
    assert (await sync_state_repo.get("github", "github-acme")).cursor == "20"


async def test_finish_run_failure_records_error_category(db_session):
    sync_run_repo = SyncRunRepository(db_session)
    sync_state_repo = SyncStateRepository(db_session)

    run = await state.start_run(
        sync_run_repo, sync_state_repo,
        source_system="github", scope_id="github-acme", correlation_id="c3",
    )
    error = Transient("connection reset", source_system="github")
    await state.finish_run_failure(sync_run_repo, sync_state_repo, run, error)

    saved_run = await sync_run_repo.get(run.id)
    assert saved_run.status.value == "FAILED"
    assert saved_run.error_category.value == "TRANSIENT"

    saved_state = await sync_state_repo.get("github", "github-acme")
    assert saved_state.status.value == "FAILED"
    assert saved_state.error == "connection reset"
