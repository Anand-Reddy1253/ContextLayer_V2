"""Context MCP — stdio transport (docs/MCP.md).

First real slice of the design in docs/MCP.md, not the full four-tool
spec. The full design (`resolve_scope`, `get_context_pack`,
`expand_evidence`, `refresh_evidence`) depends on infrastructure that
doesn't exist yet — `configs/stage-contracts.yaml`, task_ref-based scope
inference, an evidence cache with token-budget enforcement. Building
against that before it exists would mean either stubbing those pieces
(fake data, exactly what this session has spent its effort *removing*
from the demo) or blocking on a much larger build.

What's real and already tested is `catalog.search_cards` — the same
logic backing `GET /api/catalog/search-cards`, verified this session
against live Azure DevOps/GitHub/Confluence data. This server exposes
exactly that, as a single MCP tool, calling the same function directly
(not over HTTP) so there's no extra hop. Every result still carries its
`locator.native_call` — the point of this being an MCP tool instead of
a REST curl target is that an agent can call it inline in its own tool
loop, get back the exact vendor tool + params for follow-up, and hand
off to the real native GitHub/ADO/Confluence MCP tools for full content
(ADR-003 — this server is the map, never a data replica).

Run standalone: `python -m context_fabric.mcp.server_stdio`
Actor identity: none yet — authorization/RBAC (ADR-007) isn't wired
into this endpoint, same gap as the REST API today. Do not point this
at anything multi-tenant until that's built.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from mcp.server.mcpserver import MCPServer

from context_fabric.api.routes.catalog import search_cards
from context_fabric.mcp import tools
from context_fabric.persistence.session import session_scope

mcp = MCPServer("context-fabric")


# Implementations live in mcp/tools.py so an HTTP transport can register the
# same ones (docs/MCP.md). The decorator reads the signature and docstring at
# registration time — those *are* the schema and description the model sees, so
# they belong here rather than being copied across afterwards.
@mcp.tool()
async def describe_schema(kind: str | None = None) -> str:
    """What can be queried — kinds, their properties, and relations.

    Call this before writing a query. The set of kinds is not declared
    anywhere in code; it is whatever the connectors have actually synced, so
    guessing a kind name is the most likely way for a query to silently match
    nothing.

    Args:
        kind: optional, narrow the answer to one kind.
    """
    return await tools.describe_schema_tool(kind)


@mcp.tool()
async def search_entities(query: str, limit: int = 25) -> str:
    """Search entities with the structured rule grammar.

    `query` is a JSON rule group:

        {"combinator": "and", "rules": [
           {"property": "$blueprint", "operator": "=",  "value": "STORY"},
           {"property": "state",      "operator": "!=", "value": "Done"}]}

    Properties are `$`-prefixed meta-properties ($title, $blueprint, $source,
    $path, $identifier, $createdAt, $updatedAt, $syncedAt) or a bare attribute
    key from describe_schema. Operators: =, !=, contains, doesNotContain,
    beginsWith, endsWith, in, notIn, containsAny, >, >=, <, <=, between,
    notBetween, isEmpty, isNotEmpty.

    Relations traverse the graph:

        {"relation": "VERIFIES", "operator": "relatedTo", "value": "324",
         "direction": "upstream", "maxHops": 1}

    `notRelatedTo` answers "what's missing" questions — stories with no test
    coverage, repos with no owning team.

    Returns a shared `nodes` dictionary (each node once, referenced by short
    id), `anchors` pointing into it, semantic `edges` as triples, and a
    `rollup` of counts over the whole match set. Hierarchy travels as each
    node's `path`, not as edges. Anchors carry a `locator` for handing off to
    the vendor's own MCP server.

    Args:
        query: the JSON rule group.
        limit: max anchors to return (default 25).
    """
    return await tools.search_entities_tool(query, limit)


@mcp.tool()
async def aggregate_entities(
    query: str, group_by: list[str], metrics: str | None = None
) -> str:
    """Group entities and compute a metric per group — count by default.

    Same rule grammar as search_entities for the filter. Use this instead of
    fetching rows and computing something yourself — "how many open PRs per
    repository" or "average PR cycle time per repo" is one call, not N.
    Computed live, so never stale.

    Args:
        query: the JSON rule group to filter by.
        group_by: properties to group on, e.g. ["$source", "state"].
        metrics: optional JSON array of metric specs. Each is
            {"op": "count"|"avg"|"sum"|"min"|"max", "property": "..."} or,
            for a computed interval, {"op": "avg_duration_days",
            "start": "created_at", "end": "closed_at"} — the metric that
            answers "average PR cycle time", which a plain avg can't
            express since it spans two properties, not one. Add
            {"as": "name"} to control the output key. Defaults to
            [{"op": "count"}].
    """
    return await tools.aggregate_entities_tool(query, group_by, metrics)


@mcp.tool()
async def search_context(
    q: str,
    business_node_id: str | None = None,
    limit: int = 10,
) -> str:
    """Search Context Fabric's technical catalog (Azure DevOps work
    items/builds/pipelines, GitHub repos/PRs, Confluence pages) for a
    topic and return matching "cards": each match's ancestor chain
    (containment — the project/repo/space it lives in), its real
    cross-system links, its owning team/business context, and a
    `locator.native_call` giving the exact vendor MCP tool + params to
    fetch full content from the real source.

    Args:
        q: search term (matched against node name/description).
        business_node_id: optional UUID to scope results to one
            team/business unit's context space (see the Enterprise
            Graph / org tree for available team ids).
        limit: max cards to return (default 10).
    """
    parsed_id = UUID(business_node_id) if business_node_id else None
    async with session_scope() as session:
        cards: list[dict[str, Any]] = await search_cards(
            q=q, business_node_id=parsed_id, limit=limit, session=session
        )
    return json.dumps(cards, default=str)


if __name__ == "__main__":
    mcp.run(transport="stdio")
