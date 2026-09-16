"""WorkflowTemplate and WorkflowStep ORM mappings (docs/persistence.md
"workflow_template", "workflow_step"). Dialect-generic column types
throughout (Uuid/JSON/DateTime, no postgresql.* types) — same convention
persistence/orm/context_space.py already established, so this ships
dual-backend-correct (Postgres + SQLite) from the start."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime as SqlDateTime
from sqlalchemy import ForeignKey, Integer, Text
from sqlalchemy import Uuid as SqlUuid
from sqlalchemy.orm import Mapped, mapped_column

from context_fabric.persistence.orm.base import Base


class WorkflowTemplateORM(Base):
    __tablename__ = "workflow_template"

    id: Mapped[uuid.UUID] = mapped_column(SqlUuid, primary_key=True)
    context_space_id: Mapped[str] = mapped_column(
        Text, ForeignKey("context_space.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(Text, nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(SqlDateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(SqlDateTime(timezone=True), nullable=False)


class WorkflowStepORM(Base):
    __tablename__ = "workflow_step"

    id: Mapped[uuid.UUID] = mapped_column(SqlUuid, primary_key=True)
    workflow_template_id: Mapped[uuid.UUID] = mapped_column(
        SqlUuid, ForeignKey("workflow_template.id", ondelete="CASCADE"), nullable=False
    )
    order: Mapped[int] = mapped_column(Integer, nullable=False)
    source_system: Mapped[str] = mapped_column(Text, nullable=False)
    source_instance_id: Mapped[str] = mapped_column(Text, nullable=False)
    native_id: Mapped[str] = mapped_column(Text, nullable=False)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    vendor: Mapped[str] = mapped_column(Text, nullable=False)
    asset_type: Mapped[str] = mapped_column(Text, nullable=False)
    instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(SqlDateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(SqlDateTime(timezone=True), nullable=False)
