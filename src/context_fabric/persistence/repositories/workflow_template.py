"""WorkflowTemplateRepository — WorkflowTemplate + its WorkflowStep rows.
Same shape as ContextSpaceRepository: no ORM relationship() between
parent and children, so a create flushes the parent before its children
to avoid the FK-violation race that pattern's own history already found."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from context_fabric.domain.workflow_template import WorkflowStep, WorkflowTemplate
from context_fabric.persistence.orm.workflow_template import WorkflowStepORM, WorkflowTemplateORM


def _step_to_domain(row: WorkflowStepORM) -> WorkflowStep:
    return WorkflowStep(
        id=row.id,
        workflow_template_id=row.workflow_template_id,
        order=row.order,
        source_system=row.source_system,
        source_instance_id=row.source_instance_id,
        native_id=row.native_id,
        label=row.label,
        vendor=row.vendor,
        asset_type=row.asset_type,
        instructions=row.instructions,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _template_to_domain(
    row: WorkflowTemplateORM, steps: list[WorkflowStepORM]
) -> WorkflowTemplate:
    return WorkflowTemplate(
        id=row.id,
        context_space_id=row.context_space_id,
        name=row.name,
        description=row.description,
        status=row.status,  # type: ignore[arg-type]
        created_at=row.created_at,
        updated_at=row.updated_at,
        steps=[_step_to_domain(s) for s in sorted(steps, key=lambda s: s.order)],
    )


class WorkflowTemplateRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, template: WorkflowTemplate) -> WorkflowTemplate:
        row = WorkflowTemplateORM(
            id=template.id,
            context_space_id=template.context_space_id,
            name=template.name,
            description=template.description,
            status=template.status,
            created_at=template.created_at,
            updated_at=template.updated_at,
        )
        self._session.add(row)
        await self._session.flush()

        step_rows = [
            WorkflowStepORM(
                id=s.id,
                workflow_template_id=template.id,
                order=s.order,
                source_system=s.source_system,
                source_instance_id=s.source_instance_id,
                native_id=s.native_id,
                label=s.label,
                vendor=s.vendor,
                asset_type=s.asset_type,
                instructions=s.instructions,
                created_at=s.created_at,
                updated_at=s.updated_at,
            )
            for s in template.steps
        ]
        for s_row in step_rows:
            self._session.add(s_row)
        await self._session.flush()
        return await self.get(template.id)  # type: ignore[return-value]

    async def get(self, template_id: UUID) -> WorkflowTemplate | None:
        row = await self._session.get(WorkflowTemplateORM, template_id)
        if row is None:
            return None
        steps_stmt = select(WorkflowStepORM).where(
            WorkflowStepORM.workflow_template_id == template_id
        )
        steps = (await self._session.execute(steps_stmt)).scalars().all()
        return _template_to_domain(row, list(steps))

    async def list_all(self, context_space_id: str | None = None) -> list[WorkflowTemplate]:
        stmt = select(WorkflowTemplateORM)
        if context_space_id is not None:
            stmt = stmt.where(WorkflowTemplateORM.context_space_id == context_space_id)
        rows = (await self._session.execute(stmt)).scalars().all()
        templates = []
        for row in rows:
            steps_stmt = select(WorkflowStepORM).where(
                WorkflowStepORM.workflow_template_id == row.id
            )
            steps = (await self._session.execute(steps_stmt)).scalars().all()
            templates.append(_template_to_domain(row, list(steps)))
        return templates

    async def add_step(self, step: WorkflowStep) -> WorkflowStep:
        row = WorkflowStepORM(
            id=step.id,
            workflow_template_id=step.workflow_template_id,
            order=step.order,
            source_system=step.source_system,
            source_instance_id=step.source_instance_id,
            native_id=step.native_id,
            label=step.label,
            vendor=step.vendor,
            asset_type=step.asset_type,
            instructions=step.instructions,
            created_at=step.created_at,
            updated_at=step.updated_at,
        )
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return _step_to_domain(row)

    async def remove_step(self, step_id: UUID) -> None:
        row = await self._session.get(WorkflowStepORM, step_id)
        if row is not None:
            await self._session.delete(row)
            await self._session.flush()

    async def reorder_steps(
        self, template_id: UUID, ordered_step_ids: list[UUID]
    ) -> list[WorkflowStep]:
        steps_stmt = select(WorkflowStepORM).where(
            WorkflowStepORM.workflow_template_id == template_id
        )
        rows = {row.id: row for row in (await self._session.execute(steps_stmt)).scalars().all()}
        if len(ordered_step_ids) != len(set(ordered_step_ids)) or set(rows) != set(
            ordered_step_ids
        ):
            raise ValueError(
                "ordered_step_ids must be exactly the template's current step ids, "
                "each listed once, "
                f"got {sorted(str(i) for i in ordered_step_ids)} "
                f"but template has {sorted(str(i) for i in rows)}"
            )
        for index, step_id in enumerate(ordered_step_ids):
            rows[step_id].order = index
        await self._session.flush()
        return [_step_to_domain(rows[step_id]) for step_id in ordered_step_ids]

    async def delete(self, template_id: UUID) -> None:
        """Deletes the WorkflowTemplate row; its steps cascade via
        workflow_step.workflow_template_id's ondelete="CASCADE" FK
        (migration 0018) — no separate step cleanup needed here."""
        row = await self._session.get(WorkflowTemplateORM, template_id)
        if row is not None:
            await self._session.delete(row)
            await self._session.flush()
