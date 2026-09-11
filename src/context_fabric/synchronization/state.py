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
    await sync_state_repo.upsert(
        SyncState(
            source_system=run.source_system,
            scope_id=run.scope_id,
            status=SyncStatus.SUCCEEDED,
            last_successful_sync=now,
            cursor=cursor,
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
    await sync_state_repo.upsert(
        SyncState(
            source_system=run.source_system,
            scope_id=run.scope_id,
            status=SyncStatus.FAILED,
            error=str(error),
        )
    )
    return saved
