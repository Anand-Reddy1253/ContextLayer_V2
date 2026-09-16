"""SyncState and SyncRun ORM mappings (docs/persistence.md "sync_state",
"sync_run")."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from context_fabric.persistence.orm.base import Base


class SyncStateORM(Base):
    __tablename__ = "sync_state"

    source_system: Mapped[str] = mapped_column(Text, primary_key=True)
    scope_id: Mapped[str] = mapped_column(Text, primary_key=True)
    cursor: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_event_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_successful_sync: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_reconciliation: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, default="PENDING")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class SyncRunORM(Base):
    __tablename__ = "sync_run"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    source_system: Mapped[str] = mapped_column(Text, nullable=False)
    scope_id: Mapped[str] = mapped_column(Text, nullable=False)
    correlation_id: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, default="RUNNING")
    nodes_upserted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    nodes_tombstoned: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    edges_created: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_category: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
