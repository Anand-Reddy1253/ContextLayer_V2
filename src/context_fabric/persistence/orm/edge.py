"""Edge ORM mapping (docs/persistence.md "edge")."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from context_fabric.persistence.orm.base import Base


class EdgeORM(Base):
    __tablename__ = "edge"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    src_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("node.id"), nullable=False)
    dst_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("node.id"), nullable=False)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    origin: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    state: Mapped[str] = mapped_column(Text, nullable=False, default="ACTIVE")
    evidence_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("evidence.id"), nullable=True
    )
    attributes: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
