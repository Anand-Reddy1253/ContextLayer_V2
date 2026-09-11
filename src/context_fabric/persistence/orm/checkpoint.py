"""TaskCheckpoint ORM mapping (docs/persistence.md "task_checkpoint")."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from context_fabric.persistence.orm.base import Base


class TaskCheckpointORM(Base):
    __tablename__ = "task_checkpoint"

    task_ref: Mapped[str] = mapped_column(Text, primary_key=True)
    stage: Mapped[str] = mapped_column(Text, nullable=False)
    objective: Mapped[str] = mapped_column(Text, nullable=False, default="")
    context_space_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    accepted_decisions: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    completed_actions: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    files_changed: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    tests_executed: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    unresolved_questions: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    evidence_versions: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    repository_sha: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
