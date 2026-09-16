"""REST surface for retrieval primitives that aren't catalog search
(docs/RETRIEVAL.md). Currently just `resolve_scope` — the MCP tool of the
same name (mcp/tools.py) calls the identical `retrieval.scope.resolve_scope`
function; this route exists so a non-MCP caller (the UI, a harness that
isn't speaking MCP) can reach it too, without a second implementation."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from context_fabric.api.deps import get_session
from context_fabric.persistence.repositories.context_space import ContextSpaceRepository
from context_fabric.persistence.repositories.node import NodeRepository
from context_fabric.retrieval.scope import resolve_scope

router = APIRouter(prefix="/api/retrieval", tags=["retrieval"])


@router.get("/resolve-scope")
async def resolve_scope_route(
    task_ref: str,
    actor_id: str,
    context_space_override: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Which repo/team/product a task belongs to (docs/RETRIEVAL.md §1).

    Deterministic, model-call-free — see retrieval/scope.py. Never
    executes anything; only tells a caller what's there and where a
    harness should clone to act on it.
    """
    node_repo = NodeRepository(session)
    context_space_repo = ContextSpaceRepository(session)
    result = await resolve_scope(
        node_repo,
        context_space_repo,
        task_ref,
        actor_id,
        context_space_override=context_space_override,
    )
    return result.model_dump(mode="json")
