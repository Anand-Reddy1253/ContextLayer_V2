"""Context-space (logical layer / "correlation") authoring
(docs/API.md "Context spaces") — the UI's business-to-technical linking
surface."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from context_fabric.api.deps import get_session
from context_fabric.catalog import (
    add_binding,
    create_context_space_from_fields,
    delete_context_space,
    reconcile_context_space,
    remove_binding,
)
from context_fabric.domain.enums import Capability
from context_fabric.persistence.repositories.context_space import ContextSpaceRepository
from context_fabric.persistence.repositories.node import NodeRepository

router = APIRouter(prefix="/api/context-spaces", tags=["context-spaces"])


class CreateContextSpaceRequest(BaseModel):
    id: str
    name: str
    description: str = ""
    business_node_id: UUID
    owners: list[str] = []
    product: str | None = None
    teams: list[str] = []
    services: list[str] = []


class AddBindingRequest(BaseModel):
    capability: Capability
    source_system: str
    source_instance_id: str
    native_container: str
    priority: int = 0


def _space_json(space: Any) -> dict[str, Any]:
    return {
        "id": space.id,
        "name": space.name,
        "description": space.description,
        "owners": space.owners,
        "product": space.product,
        "teams": space.teams,
        "services": space.services,
        "status": space.status,
        "business_node_id": str(space.business_node_id),
        "bindings": [
            {
                "id": str(b.id),
                "capability": b.capability.value,
                "source_system": b.source_system,
                "source_instance_id": b.source_instance_id,
                "native_container": b.native_container,
                "priority": b.priority,
            }
            for b in space.bindings
        ],
    }


@router.get("")
async def list_spaces(session: AsyncSession = Depends(get_session)) -> list[dict[str, Any]]:
    repo = ContextSpaceRepository(session)
    spaces = await repo.list_all()
    return [_space_json(s) for s in spaces]


@router.get("/{context_space_id:path}/reconcile")
async def reconcile_space(
    context_space_id: str, session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    """The correlation status view: for each binding, is the native
    location it points at actually present in the synced technical
    graph? (docs/phases/PHASE-08.md's reconcile, surfaced in the UI.)

    Registered before the generic get_space route below — FastAPI/Starlette
    matches routes in registration order, so the more specific "/reconcile"
    suffix must be tried first or get_space's path converter swallows it."""
    repo = ContextSpaceRepository(session)
    space = await repo.get(context_space_id)
    if space is None:
        raise HTTPException(404, "context space not found")

    report = await reconcile_context_space(NodeRepository(session), space)
    return {
        "context_space_id": report.context_space_id,
        "all_resolved": report.all_resolved,
        "results": [
            {
                "binding_id": str(r.binding.id),
                "capability": r.binding.capability.value,
                "source_system": r.binding.source_system,
                "native_container": r.binding.native_container,
                "resolved": r.resolved,
                "node_id": str(r.node_id) if r.node_id else None,
            }
            for r in report.results
        ],
    }


@router.get("/{context_space_id:path}")
async def get_space(
    context_space_id: str, session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    space = await ContextSpaceRepository(session).get(context_space_id)
    if space is None:
        raise HTTPException(404, "context space not found")
    return _space_json(space)


@router.post("", status_code=201)
async def create_space(
    body: CreateContextSpaceRequest, session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    node_repo = NodeRepository(session)
    business_node = await node_repo.get(body.business_node_id)
    if business_node is None:
        raise HTTPException(400, f"business node {body.business_node_id} not found")

    repo = ContextSpaceRepository(session)
    existing = await repo.get(body.id)
    if existing is not None:
        raise HTTPException(409, f"context space {body.id!r} already exists")

    space = await create_context_space_from_fields(
        repo,
        id=body.id,
        name=body.name,
        description=body.description,
        business_node_id=body.business_node_id,
        owners=body.owners,
        product=body.product,
        teams=body.teams,
        services=body.services,
    )
    return _space_json(space)


@router.post("/{context_space_id:path}/bindings", status_code=201)
async def add_space_binding(
    context_space_id: str, body: AddBindingRequest, session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    repo = ContextSpaceRepository(session)
    space = await repo.get(context_space_id)
    if space is None:
        raise HTTPException(404, "context space not found")

    binding = await add_binding(
        repo,
        context_space_id,
        capability=body.capability,
        source_system=body.source_system,
        source_instance_id=body.source_instance_id,
        native_container=body.native_container,
        priority=body.priority,
    )
    return {
        "id": str(binding.id),
        "capability": binding.capability.value,
        "source_system": binding.source_system,
        "source_instance_id": binding.source_instance_id,
        "native_container": binding.native_container,
        "priority": binding.priority,
    }


@router.delete("/{context_space_id:path}/bindings/{binding_id}", status_code=204)
async def delete_space_binding(
    context_space_id: str, binding_id: UUID, session: AsyncSession = Depends(get_session)
) -> None:
    await remove_binding(ContextSpaceRepository(session), binding_id)


@router.delete("/{context_space_id:path}", status_code=204)
async def delete_space(
    context_space_id: str, session: AsyncSession = Depends(get_session)
) -> None:
    """Registered after /bindings/{binding_id} above — same
    registration-order lesson as reconcile_space: a bare :path DELETE
    here would otherwise swallow the more specific binding-delete route
    first."""
    await delete_context_space(ContextSpaceRepository(session), context_space_id)
