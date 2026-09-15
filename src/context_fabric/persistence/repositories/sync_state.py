"""SyncStateRepository."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from context_fabric.domain.sync import SyncState
from context_fabric.persistence.orm.sync import SyncStateORM


def _to_domain(row: SyncStateORM) -> SyncState:
    return SyncState(
        source_system=row.source_system,
        scope_id=row.scope_id,
        cursor=row.cursor,
        last_event_id=row.last_event_id,
        last_successful_sync=row.last_successful_sync,
        last_reconciliation=row.last_reconciliation,
        status=row.status,  # type: ignore[arg-type]
        error=row.error,
    )


class SyncStateRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(self, state: SyncState) -> SyncState:
        row = await self._session.get(SyncStateORM, (state.source_system, state.scope_id))
        if row is None:
            row = SyncStateORM(source_system=state.source_system, scope_id=state.scope_id)
            self._session.add(row)
        row.cursor = state.cursor
        row.last_event_id = state.last_event_id
        row.last_successful_sync = state.last_successful_sync
        row.last_reconciliation = state.last_reconciliation
        row.status = state.status.value
        row.error = state.error
        await self._session.flush()
        return _to_domain(row)

    async def get(self, source_system: str, scope_id: str) -> SyncState | None:
        row = await self._session.get(SyncStateORM, (source_system, scope_id))
        return _to_domain(row) if row is not None else None

    async def list_all(self) -> list[SyncState]:
        """Every connector instance's current sync state — the source of
        truth a health/staleness view reads, rather than each caller
        re-deriving it from SyncRun history."""
        rows = (await self._session.execute(select(SyncStateORM))).scalars().all()
        return [_to_domain(r) for r in rows]
