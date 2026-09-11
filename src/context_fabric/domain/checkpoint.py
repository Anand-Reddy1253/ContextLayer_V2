"""TaskCheckpoint — durable task state (ADR-008, docs/DOMAIN_MODEL.md).

Conversation history is not state. A checkpoint is the record of task
progress that survives a restart or a context compaction; packs and
summaries are caches built from it plus current graph state, never from a
previous pack's prose (ADR-008: "a summary is never recursively
re-summarized").
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TaskCheckpoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_ref: str
    stage: str
    objective: str = ""
    context_space_ids: list[str] = Field(default_factory=list)
    accepted_decisions: list[str] = Field(default_factory=list)
    completed_actions: list[str] = Field(default_factory=list)
    files_changed: list[str] = Field(default_factory=list)
    tests_executed: list[str] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)
    evidence_versions: dict[str, str] = Field(default_factory=dict)
    repository_sha: str | None = None
    updated_at: datetime
