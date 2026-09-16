"""Workflow template authoring (docs/API.md) — the UI's "define a
template" surface: a named, ordered sequence of steps, each a specific
AI_ASSET picked from the catalog, that a harness later pulls and
executes. Mirrors api/routes/context_spaces.py's shape."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from context_fabric.api.deps import get_session
from context_fabric.catalog import (
    AiAssetNotFound,
    NotAnAiAsset,
    add_step,
    create_workflow_template,
    delete_workflow_template,
    get_workflow_template,
    list_workflow_templates,
    remove_step,
    reorder_steps,
)
from context_fabric.persistence.repositories.node import NodeRepository
from context_fabric.persistence.repositories.workflow_template import WorkflowTemplateRepository

router = APIRouter(prefix="/api/workflow-templates", tags=["workflow-templates"])


class CreateWorkflowTemplateRequest(BaseModel):
    context_space_id: str
    name: str
    description: str = ""


class AddStepRequest(BaseModel):
    source_system: str
    source_instance_id: str
    native_id: str
    instructions: str | None = None


class ReorderStepsRequest(BaseModel):
    step_ids: list[UUID]


def _step_json(step: Any) -> dict[str, Any]:
    return {
        "id": str(step.id),
        "workflow_template_id": str(step.workflow_template_id),
        "order": step.order,
        "source_system": step.source_system,
        "source_instance_id": step.source_instance_id,
        "native_id": step.native_id,
        "label": step.label,
        "vendor": step.vendor,
        "asset_type": step.asset_type,
        "instructions": step.instructions,
    }


def _template_json(template: Any) -> dict[str, Any]:
    return {
        "id": str(template.id),
        "context_space_id": template.context_space_id,
        "name": template.name,
        "description": template.description,
        "status": template.status,
        "steps": [_step_json(s) for s in template.steps],
    }


@router.get("")
async def list_templates(
    context_space_id: str | None = None, session: AsyncSession = Depends(get_session)
) -> list[dict[str, Any]]:
    repo = WorkflowTemplateRepository(session)
    templates = await list_workflow_templates(repo, context_space_id)
    return [_template_json(t) for t in templates]


@router.get("/{template_id}")
async def get_template(
    template_id: UUID, session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    repo = WorkflowTemplateRepository(session)
    template = await get_workflow_template(repo, template_id)
    if template is None:
        raise HTTPException(404, "workflow template not found")
    return _template_json(template)


@router.post("", status_code=201)
async def create_template(
    body: CreateWorkflowTemplateRequest, session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    repo = WorkflowTemplateRepository(session)
    template = await create_workflow_template(
        repo,
        context_space_id=body.context_space_id,
        name=body.name,
        description=body.description,
    )
    return _template_json(template)


@router.delete("/{template_id}", status_code=204)
async def delete_template(template_id: UUID, session: AsyncSession = Depends(get_session)) -> None:
    await delete_workflow_template(WorkflowTemplateRepository(session), template_id)


@router.post("/{template_id}/steps", status_code=201)
async def add_template_step(
    template_id: UUID, body: AddStepRequest, session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    template_repo = WorkflowTemplateRepository(session)
    if await get_workflow_template(template_repo, template_id) is None:
        raise HTTPException(404, "workflow template not found")

    node_repo = NodeRepository(session)
    try:
        step = await add_step(
            template_repo,
            node_repo,
            template_id,
            source_system=body.source_system,
            source_instance_id=body.source_instance_id,
            native_id=body.native_id,
            instructions=body.instructions,
        )
    except (AiAssetNotFound, NotAnAiAsset) as exc:
        raise HTTPException(400, str(exc)) from exc
    return _step_json(step)


@router.delete("/{template_id}/steps/{step_id}", status_code=204)
async def remove_template_step(
    template_id: UUID, step_id: UUID, session: AsyncSession = Depends(get_session)
) -> None:
    await remove_step(WorkflowTemplateRepository(session), step_id)


@router.post("/{template_id}/steps/reorder")
async def reorder_template_steps(
    template_id: UUID, body: ReorderStepsRequest, session: AsyncSession = Depends(get_session)
) -> list[dict[str, Any]]:
    repo = WorkflowTemplateRepository(session)
    try:
        steps = await reorder_steps(repo, template_id, body.step_ids)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return [_step_json(s) for s in steps]
