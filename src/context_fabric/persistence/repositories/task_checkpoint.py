"""TaskCheckpointRepository."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from context_fabric.domain.checkpoint import TaskCheckpoint
from context_fabric.persistence.orm.checkpoint import TaskCheckpointORM


def _to_domain(row: TaskCheckpointORM) -> TaskCheckpoint:
    return TaskCheckpoint(
        task_ref=row.task_ref,
        stage=row.stage,
        objective=row.objective,
        context_space_ids=row.context_space_ids,
        accepted_decisions=row.accepted_decisions,
        completed_actions=row.completed_actions,
        files_changed=row.files_changed,
        tests_executed=row.tests_executed,
        unresolved_questions=row.unresolved_questions,
        evidence_versions=row.evidence_versions,
        repository_sha=row.repository_sha,
        updated_at=row.updated_at,
    )


class TaskCheckpointRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, checkpoint: TaskCheckpoint) -> TaskCheckpoint:
        row = await self._session.get(TaskCheckpointORM, checkpoint.task_ref)
        if row is None:
            row = TaskCheckpointORM(task_ref=checkpoint.task_ref)
            self._session.add(row)
        row.stage = checkpoint.stage
        row.objective = checkpoint.objective
        row.context_space_ids = checkpoint.context_space_ids
        row.accepted_decisions = checkpoint.accepted_decisions
        row.completed_actions = checkpoint.completed_actions
        row.files_changed = checkpoint.files_changed
        row.tests_executed = checkpoint.tests_executed
        row.unresolved_questions = checkpoint.unresolved_questions
        row.evidence_versions = checkpoint.evidence_versions
        row.repository_sha = checkpoint.repository_sha
        row.updated_at = checkpoint.updated_at
        await self._session.flush()
        return _to_domain(row)

    async def get(self, task_ref: str) -> TaskCheckpoint | None:
        row = await self._session.get(TaskCheckpointORM, task_ref)
        return _to_domain(row) if row is not None else None
