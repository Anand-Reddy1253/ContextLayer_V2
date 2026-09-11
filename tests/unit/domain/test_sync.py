from context_fabric.domain.enums import SyncStatus
from context_fabric.domain.sync import SyncRun, SyncState


def test_sync_state_defaults():
    state = SyncState(source_system="azure_devops", scope_id="TalentFlow")
    assert state.status is SyncStatus.PENDING
    assert state.cursor is None


def test_sync_run_tracks_counts(now):
    run = SyncRun(
        source_system="github",
        scope_id="acme-org",
        correlation_id="corr-1",
        started_at=now,
        nodes_upserted=5,
        edges_created=3,
    )
    assert run.status is SyncStatus.RUNNING
    assert run.nodes_upserted == 5
    assert run.error_category is None
