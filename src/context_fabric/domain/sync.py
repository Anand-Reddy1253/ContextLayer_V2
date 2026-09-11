"""SyncState and SyncRun (docs/DOMAIN_MODEL.md).

SyncState is the small "current cursor" row per (source_system, scope_id).
SyncRun is one row per sync invocation, added for observability so history
stays queryable without growing SyncState (docs/phases/PHASE-06.md,
PHASE-14.md).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from context_fabric.domain.enums import ErrorCategory, SyncStatus


class SyncState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_system: str
    scope_id: str
    cursor: str | None = None
    last_event_id: str | None = None
    last_successful_sync: datetime | None = None
    last_reconciliation: datetime | None = None
    status: SyncStatus = SyncStatus.PENDING
    error: str | None = None


class SyncRun(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    source_system: str
    scope_id: str
    correlation_id: str
    started_at: datetime
    finished_at: datetime | None = None
    status: SyncStatus = SyncStatus.RUNNING
    nodes_upserted: int = 0
    nodes_tombstoned: int = 0
    edges_created: int = 0
    error_category: ErrorCategory | None = None
    error_detail: str | None = None
