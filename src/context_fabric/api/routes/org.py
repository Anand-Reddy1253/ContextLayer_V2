"""Business tree CRUD (docs/API.md "Org")."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from context_fabric.api.deps import get_session
from context_fabric.catalog import (
    BusinessNodeHasDependents,
    create_business_node,
    delete_business_node,
    list_business_tree,
    load_business_tree_config,
    seed_business_tree,
    update_business_node,
)
from context_fabric.persistence.repositories.context_space import ContextSpaceRepository
from context_fabric.persistence.repositories.node import NodeRepository

router = APIRouter(prefix="/api/org", tags=["org"])


class CreateBusinessNodeRequest(BaseModel):
    parent_id: UUID | None = None
    kind: str
    name: str
    description: str | None = None
    owners: list[str] = []


def _node_json(node: Any) -> dict[str, Any]:
    return {
        "id": str(node.id),
        "parent_id": str(node.parent_id) if node.parent_id else None,
        "kind": node.kind,
        "name": node.name,
        "description": node.description,
        "owners": node.owners,
        "path": node.path,
        "attributes": node.attributes,
    }


# The "business context" fields (docs/UI.md "Business Hierarchy") — stored
# inside Node.attributes (no schema of their own, same loosely-typed
# pattern every TECHNICAL node's attributes already uses), but named
# explicitly here so PATCH accepts them as first-class request fields
# rather than a freehand dict a caller could put anything into.
_BUSINESS_CONTEXT_ATTRIBUTE_FIELDS = (
    "criticality_tier",
    "compliance_scope",
    "stakeholders",
    "communication_channel",
)


class UpdateBusinessNodeRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    kind: str | None = None
    owners: list[str] | None = None
    criticality_tier: str | None = None
    compliance_scope: list[str] | None = None
    stakeholders: list[str] | None = None
    communication_channel: dict[str, str] | None = None


@router.get("/tree")
async def get_tree(session: AsyncSession = Depends(get_session)) -> list[dict[str, Any]]:
    nodes = await list_business_tree(NodeRepository(session))
    return [_node_json(n) for n in nodes]


@router.post("/nodes", status_code=201)
async def create_node(
    body: CreateBusinessNodeRequest, session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    node_repo = NodeRepository(session)
    try:
        node = await create_business_node(
            node_repo,
            parent_id=body.parent_id,
            kind=body.kind,
            name=body.name,
            description=body.description,
            owners=body.owners,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return _node_json(node)


@router.patch("/nodes/{node_id}")
async def update_node(
    node_id: UUID, body: UpdateBusinessNodeRequest, session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    """Partial update — omit a field to leave it unchanged; pass a
    business-context field explicitly as null to clear it. `name`/
    `description`/`kind`/`owners` are the node's existing fields; the
    other four are the "business context" attributes (docs/UI.md
    "Business Hierarchy")."""
    provided = body.model_fields_set
    attributes = {
        f: getattr(body, f) for f in _BUSINESS_CONTEXT_ATTRIBUTE_FIELDS if f in provided
    }
    node_repo = NodeRepository(session)
    try:
        node = await update_business_node(
            node_repo,
            node_id,
            name=body.name if "name" in provided else None,
            description=body.description if "description" in provided else None,
            kind=body.kind if "kind" in provided else None,
            owners=body.owners if "owners" in provided else None,
            attributes=attributes or None,
        )
    except ValueError as exc:
        status = 404 if "not found" in str(exc) else 400
        raise HTTPException(status, str(exc)) from exc
    return _node_json(node)


@router.delete("/nodes/{node_id}", status_code=204)
async def delete_node(node_id: UUID, session: AsyncSession = Depends(get_session)) -> None:
    """Blocked (400), not cascaded, if a child node or a context space
    still depends on it — docs/UI.md "Business Layer" delete."""
    try:
        await delete_business_node(
            NodeRepository(session), ContextSpaceRepository(session), node_id
        )
    except BusinessNodeHasDependents as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/seed-example", status_code=201)
async def seed_example_tree(session: AsyncSession = Depends(get_session)) -> list[dict[str, Any]]:
    """Loads configs/business-tree/acme.yaml — a "quick start" so the
    UI's business-tree screen isn't empty before anyone has manually
    created a node. Idempotent (seed_business_tree skips existing paths)."""
    node_repo = NodeRepository(session)
    results = await seed_business_tree(node_repo, load_business_tree_config())
    return [_node_json(n) for n in results.values()]
