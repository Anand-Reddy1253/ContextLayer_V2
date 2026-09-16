"""Bounded traversal over `edge` (docs/persistence.md "Query patterns":
recursive CTE over edge, filtered by type IN (...) and state = 'ACTIVE').

ltree ancestor/descendant queries over `node.path` already live on
NodeRepository (list_descendants/list_ancestors_of_path, Phase 2) — this
module is specifically the edge-graph walk that didn't exist before
Phase 7: "what's reachable from this node, within N hops, along these
edge types."

Only ACTIVE, non-deleted edges are ever traversed — a PROPOSED
(unconfirmed) extracted edge is not yet part of the trusted graph
(docs/DOMAIN_MODEL.md "EdgeState").
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

from context_fabric.domain.enums import EdgeType
from context_fabric.domain.node import Node
from context_fabric.persistence.repositories.node import NodeRepository

Direction = Literal["out", "in", "both"]


async def _traverse_one_direction(
    session: AsyncSession,
    root_id: UUID,
    edge_types: list[EdgeType] | None,
    max_hops: int,
    direction: Literal["out", "in"],
) -> set[UUID]:
    start_col, root_col = ("dst_id", "src_id") if direction == "out" else ("src_id", "dst_id")

    # Not `type = ANY(:edge_types)` — that's Postgres's array-parameter
    # syntax, and SQLite has no array type at all. `type IN :edge_types`
    # with an `expanding=True` bindparam is SQLAlchemy's dialect-agnostic
    # equivalent, expanding to the right list-literal SQL for whichever
    # backend is connected.
    base_type_clause = "AND type IN :edge_types" if edge_types else ""
    step_type_clause = "AND e.type IN :edge_types" if edge_types else ""

    sql = text(
        f"""
        WITH RECURSIVE reachable(node_id, depth) AS (
            SELECT {start_col} AS node_id, 1 AS depth
            FROM edge
            WHERE {root_col} = :root_id
              AND state = 'ACTIVE'
              AND deleted_at IS NULL
              {base_type_clause}
            UNION
            SELECT e.{start_col} AS node_id, r.depth + 1 AS depth
            FROM edge e
            JOIN reachable r ON e.{root_col} = r.node_id
            WHERE e.state = 'ACTIVE'
              AND e.deleted_at IS NULL
              AND r.depth < :max_hops
              {step_type_clause}
        )
        SELECT DISTINCT node_id FROM reachable
        """
    )
    params: dict[str, object] = {"root_id": root_id, "max_hops": max_hops}
    if edge_types:
        sql = sql.bindparams(bindparam("edge_types", expanding=True))
        params["edge_types"] = [t.value for t in edge_types]

    result = await session.execute(sql, params)
    return {row[0] for row in result}


async def traverse(
    session: AsyncSession,
    root_id: UUID,
    *,
    edge_types: list[EdgeType] | None = None,
    max_hops: int = 3,
    direction: Direction = "out",
    include_root: bool = False,
) -> list[Node]:
    """Every node reachable from `root_id` within `max_hops`, following
    only `edge_types` (all types if None) in `direction`. `"both"` unions
    the forward and backward reachable sets — not a single combined
    recursive query, since UNION-based cycle-safe recursion for two
    directions at once is materially more complex without adding
    capability this project's scope needs.
    """
    if direction == "both":
        node_ids = await _traverse_one_direction(session, root_id, edge_types, max_hops, "out")
        node_ids |= await _traverse_one_direction(session, root_id, edge_types, max_hops, "in")
    else:
        node_ids = await _traverse_one_direction(session, root_id, edge_types, max_hops, direction)

    node_ids.discard(root_id)
    if include_root:
        node_ids.add(root_id)

    return await NodeRepository(session).get_many(list(node_ids))
