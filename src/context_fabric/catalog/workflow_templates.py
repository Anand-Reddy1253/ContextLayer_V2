"""WorkflowTemplate + WorkflowStep write path (domain/workflow_template.py),
backed by persistence/repositories/workflow_template.py — the UI-form
write path for authoring a named, ordered sequence of steps a harness
later pulls and executes. Context Fabric never runs one of these; it only
stores and serves it (AGENTS.md §4/§6).
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from context_fabric.domain.workflow_template import WorkflowStep, WorkflowTemplate
from context_fabric.persistence.repositories.node import NodeRepository
from context_fabric.persistence.repositories.workflow_template import WorkflowTemplateRepository


class AiAssetNotFound(ValueError):
    """Raised when add_step's (source_system, source_instance_id,
    native_id) doesn't resolve to a synced node at all."""


class NotAnAiAsset(ValueError):
    """Raised when it resolves, but to a node that isn't kind AI_ASSET —
    a template step must be a real, runnable agent/skill/rule/command
    definition, not an arbitrary catalog entry."""


async def create_workflow_template(
    template_repo: WorkflowTemplateRepository,
    *,
    context_space_id: str,
    name: str,
    description: str = "",
) -> WorkflowTemplate:
    now = datetime.now(UTC)
    template = WorkflowTemplate(
        context_space_id=context_space_id,
        name=name,
        description=description,
        created_at=now,
        updated_at=now,
    )
    return await template_repo.create(template)


async def get_workflow_template(
    template_repo: WorkflowTemplateRepository, template_id: UUID
) -> WorkflowTemplate | None:
    return await template_repo.get(template_id)


async def list_workflow_templates(
    template_repo: WorkflowTemplateRepository, context_space_id: str | None = None
) -> list[WorkflowTemplate]:
    return await template_repo.list_all(context_space_id)


async def delete_workflow_template(
    template_repo: WorkflowTemplateRepository, template_id: UUID
) -> None:
    await template_repo.delete(template_id)


async def add_step(
    template_repo: WorkflowTemplateRepository,
    node_repo: NodeRepository,
    template_id: UUID,
    *,
    source_system: str,
    source_instance_id: str,
    native_id: str,
    instructions: str | None = None,
) -> WorkflowStep:
    """Resolves the node now (must already be synced) and snapshots its
    display fields onto the step — same reasoning as Binding.native_container
    storing the container directly rather than a live join, so the
    template keeps displaying correctly even if the repo is later
    unsynced. Validated eagerly here (unlike add_binding, which doesn't
    validate) because, unlike a binding's container, the node is
    guaranteed to already exist — there's no config-file authoring path
    for this that could legitimately reference something not yet synced.
    """
    node = await node_repo.get_by_technical_identity(source_system, source_instance_id, native_id)
    if node is None:
        raise AiAssetNotFound(
            f"no synced node for {source_system}:{source_instance_id}:{native_id}"
        )
    if node.kind != "AI_ASSET":
        raise NotAnAiAsset(f"{source_system}:{native_id} is kind {node.kind!r}, not AI_ASSET")

    existing = await template_repo.get(template_id)
    next_order = len(existing.steps) if existing is not None else 0

    now = datetime.now(UTC)
    step = WorkflowStep(
        workflow_template_id=template_id,
        order=next_order,
        source_system=source_system,
        source_instance_id=source_instance_id,
        native_id=native_id,
        label=node.name,
        vendor=str(node.attributes.get("vendor", "")),
        asset_type=str(node.attributes.get("asset_type", "")),
        instructions=instructions,
        created_at=now,
        updated_at=now,
    )
    return await template_repo.add_step(step)


async def remove_step(template_repo: WorkflowTemplateRepository, step_id: UUID) -> None:
    await template_repo.remove_step(step_id)


async def reorder_steps(
    template_repo: WorkflowTemplateRepository, template_id: UUID, ordered_step_ids: list[UUID]
) -> list[WorkflowStep]:
    return await template_repo.reorder_steps(template_id, ordered_step_ids)
