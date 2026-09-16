"""Evidence ORM mapping (docs/persistence.md "evidence")."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from context_fabric.persistence.orm.base import Base


class EvidenceORM(Base):
    __tablename__ = "evidence"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    node_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("node.id"), nullable=False)
    source_system: Mapped[str] = mapped_column(Text, nullable=False)
    source_instance_id: Mapped[str] = mapped_column(Text, nullable=False)
    native_id: Mapped[str] = mapped_column(Text, nullable=False)
    source_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    uri: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    acl_ref: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
