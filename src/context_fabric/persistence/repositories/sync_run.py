"""SyncRunRepository.

Not in Phase 2's original repository list — added in Phase 6 once
synchronization/ actually needed to write sync_run rows (the table itself
was created by Phase 2's migration 0006 alongside sync_state)."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from context_fabric.domain.enums import ErrorCategory, SyncStatus
from context_fabric.domain.sync import SyncRun
from context_fabric.persistence.orm.sync import SyncRunORM


def _to_domain(row: SyncRunORM) -> SyncRun:
    return SyncRun(
        id=row.id,
        source_system=row.source_system,
        scope_id=row.scope_id,
        correlation_id=row.correlation_id,
        started_at=row.started_at,
        finished_at=row.finished_at,
        status=SyncStatus(row.status),
        nodes_upserted=row.nodes_upserted,
        nodes_tombstoned=row.nodes_tombstoned,
        edges_created=row.edges_created,
        error_category=ErrorCategory(row.error_category) if row.error_category else None,
        error_detail=row.error_detail,
    )


class SyncRunRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, run: SyncRun) -> SyncRun:
        row = SyncRunORM(
            id=run.id,
            source_system=run.source_system,
            scope_id=run.scope_id,
            correlation_id=run.correlation_id,
            started_at=run.started_at,
            finished_at=run.finished_at,
            status=run.status.value,
            nodes_upserted=run.nodes_upserted,
            nodes_tombstoned=run.nodes_tombstoned,
            edges_created=run.edges_created,
            error_category=run.error_category.value if run.error_category else None,
            error_detail=run.error_detail,
        )
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return _to_domain(row)

    async def update(self, run: SyncRun) -> SyncRun:
        row = await self._session.get(SyncRunORM, run.id)
        if row is None:
            raise ValueError(f"cannot update: no sync_run with id={run.id}")
        row.finished_at = run.finished_at
        row.status = run.status.value
        row.nodes_upserted = run.nodes_upserted
        row.nodes_tombstoned = run.nodes_tombstoned
        row.edges_created = run.edges_created
        row.error_category = run.error_category.value if run.error_category else None
        row.error_detail = run.error_detail
        await self._session.flush()
        await self._session.refresh(row)
        return _to_domain(row)

    async def get(self, run_id: UUID) -> SyncRun | None:
        row = await self._session.get(SyncRunORM, run_id)
        return _to_domain(row) if row is not None else None

    async def list_for_scope(self, source_system: str, scope_id: str) -> list[SyncRun]:
        stmt = (
            select(SyncRunORM)
            .where(SyncRunORM.source_system == source_system, SyncRunORM.scope_id == scope_id)
            .order_by(SyncRunORM.started_at.desc())
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [_to_domain(r) for r in rows]
