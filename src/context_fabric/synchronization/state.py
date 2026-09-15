"""sync_state / sync_run bookkeeping (docs/DOMAIN_MODEL.md "SyncState",
"SyncRun"). One SyncRun row per invocation; SyncState holds the small
"current cursor/status" summary per (source_system, scope_id) — here,
scope_id is the connector instance id (e.g. "ado-acme"), since the
orchestrator syncs a whole connector instance in one pass, not a
sub-container.
"""

from __future__ import annotations

from datetime import UTC, datetime

from context_fabric.domain.enums import SyncStatus
from context_fabric.domain.errors import ConnectorError
from context_fabric.domain.sync import SyncRun, SyncState
from context_fabric.persistence.repositories.sync_run import SyncRunRepository
from context_fabric.persistence.repositories.sync_state import SyncStateRepository


async def start_run(
    sync_run_repo: SyncRunRepository,
    sync_state_repo: SyncStateRepository,
    *,
    source_system: str,
    scope_id: str,
    correlation_id: str,
) -> SyncRun:
    run = SyncRun(
        source_system=source_system,
        scope_id=scope_id,
        correlation_id=correlation_id,
        started_at=datetime.now(UTC),
        status=SyncStatus.RUNNING,
    )
    created = await sync_run_repo.create(run)
    await sync_state_repo.upsert(
        SyncState(source_system=source_system, scope_id=scope_id, status=SyncStatus.RUNNING)
    )
    return created


async def finish_run_success(
    sync_run_repo: SyncRunRepository,
    sync_state_repo: SyncStateRepository,
    run: SyncRun,
    *,
    nodes_upserted: int,
    nodes_tombstoned: int,
    edges_created: int,
    cursor: str | None = None,
    walk_complete: bool = True,
) -> SyncRun:
    now = datetime.now(UTC)
    updated = run.model_copy(
        update={
            "finished_at": now,
            "status": SyncStatus.SUCCEEDED,
            "nodes_upserted": nodes_upserted,
            "nodes_tombstoned": nodes_tombstoned,
            "edges_created": edges_created,
        }
    )
    saved = await sync_run_repo.update(updated)
    # Preserve the previous last_reconciliation on a non-full pass rather
    # than blanking it — an incremental run succeeding doesn't mean the
    # last *full* walk is any less current, it just didn't run one this
    # time. Only a genuinely complete walk (orchestrator.SyncStats.
    # walk_complete — see its docstring) is allowed to advance this.
    #
    # Same reasoning for `cursor`: a full sync pass has no incremental
    # cursor of its own to report and calls this with cursor=None — if
    # that blanked the stored value, every full (e.g. nightly
    # reconciliation) run would erase an incremental connector's delta
    # watermark, forcing it back to a from-scratch lookback window next
    # time for no reason. Preserved unless a real cursor is actually
    # supplied.
    existing = await sync_state_repo.get(run.source_system, run.scope_id)
    last_reconciliation = now if walk_complete else (
        existing.last_reconciliation if existing else None
    )
    effective_cursor = cursor if cursor is not None else (existing.cursor if existing else None)
    await sync_state_repo.upsert(
        SyncState(
            source_system=run.source_system,
            scope_id=run.scope_id,
            status=SyncStatus.SUCCEEDED,
            last_successful_sync=now,
            last_reconciliation=last_reconciliation,
            cursor=effective_cursor,
            last_event_id=existing.last_event_id if existing else None,
        )
    )
    return saved


async def finish_run_failure(
    sync_run_repo: SyncRunRepository,
    sync_state_repo: SyncStateRepository,
    run: SyncRun,
    error: ConnectorError,
) -> SyncRun:
    now = datetime.now(UTC)
    updated = run.model_copy(
        update={
            "finished_at": now,
            "status": SyncStatus.FAILED,
            "error_category": error.category,
            "error_detail": str(error),
        }
    )
    saved = await sync_run_repo.update(updated)
    # A real bug, found via the sync-health endpoint this same change adds:
    # constructing a bare SyncState here (only status/error set) meant
    # `upsert` overwrote the *entire* row on every failure, blanking
    # last_successful_sync/last_reconciliation/cursor even for a connector
    # that had synced successfully many times before and just hit one
    # transient error. A health view built on that would report "never
    # synced" the moment any single sync attempt failed, which is a worse,
    # false-negative version of the exact "can't tell what's actually
    # stale" problem the health endpoint exists to fix. Only status and
    # error should change on failure — everything else about the
    # connector's sync history is still true.
    existing = await sync_state_repo.get(run.source_system, run.scope_id)
    await sync_state_repo.upsert(
        SyncState(
            source_system=run.source_system,
            scope_id=run.scope_id,
            status=SyncStatus.FAILED,
            error=str(error),
            last_successful_sync=existing.last_successful_sync if existing else None,
            last_reconciliation=existing.last_reconciliation if existing else None,
            cursor=existing.cursor if existing else None,
            last_event_id=existing.last_event_id if existing else None,
        )
    )
    return saved
