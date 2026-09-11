"""ContextSpace and Binding ORM mappings (docs/persistence.md "context_space",
"binding")."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column

from context_fabric.persistence.orm.base import Base


class ContextSpaceORM(Base):
    __tablename__ = "context_space"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    business_node_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("node.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    owners: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    product: Mapped[str | None] = mapped_column(Text, nullable=True)
    teams: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    services: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="active")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)


class BindingORM(Base):
    __tablename__ = "binding"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    context_space_id: Mapped[str] = mapped_column(
        Text, ForeignKey("context_space.id", ondelete="CASCADE"), nullable=False
    )
    capability: Mapped[str] = mapped_column(Text, nullable=False)
    source_system: Mapped[str] = mapped_column(Text, nullable=False)
    source_instance_id: Mapped[str] = mapped_column(Text, nullable=False)
    native_container: Mapped[str] = mapped_column(Text, nullable=False)
    origin: Mapped[str] = mapped_column(Text, nullable=False, default="HUMAN")
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
