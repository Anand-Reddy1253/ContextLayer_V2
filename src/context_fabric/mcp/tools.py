"""Context MCP tool implementations, shared across transports (docs/MCP.md).

Transport-agnostic on purpose: `server_stdio.py` registers these, and an HTTP
transport would register the same functions rather than reimplementing them.
Each returns a JSON string because that is what an MCP tool result is.

Every tool here is read-only. Context Fabric holds read credentials for each
vendor and has no write path to any of them — an agent that needs to comment on
a PR goes to that vendor's own MCP server with its own identity, which keeps the
audit trail attached to whoever actually acted.
"""

from __future__ import annotations

import json
from typing import Any

from context_fabric.api.routes.catalog import (
    aggregate_entities,
    describe_schema,
    search_entities,
)
from context_fabric.domain.query import AggregateQuery, EntityQuery, RuleGroup
from context_fabric.persistence.session import session_scope


def _parse_rule_group(query: str | dict[str, Any] | None) -> RuleGroup:
    """Accept the rule tree as either a JSON string or an already-decoded dict.

    Models hand tool arguments over inconsistently — sometimes a nested object,
    sometimes a string containing JSON — and failing on the string form would
    be a confusing dead end for something this easy to accept.
    """
    if query is None or query == "":
        return RuleGroup()
    if isinstance(query, str):
        try:
            decoded = json.loads(query)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"query must be a JSON object, got unparseable string: {exc}"
            ) from exc
    else:
        decoded = query
    if not isinstance(decoded, dict):
        raise ValueError("query must be a JSON object with 'combinator' and 'rules'")
    return RuleGroup.model_validate(decoded)


async def describe_schema_tool(kind: str | None = None) -> str:
    """What can be queried — kinds, their properties, and relations.

    Call this before writing a query. The set of kinds is not declared
    anywhere in code; it is whatever the connectors have actually synced, so
    guessing a kind name is the most likely way for a query to silently match
    nothing.
    """
    async with session_scope() as session:
        result = await describe_schema(kind=kind, session=session)
    return json.dumps(result, default=str)


async def search_entities_tool(query: str, limit: int = 25) -> str:
    """Search entities with the structured rule grammar.

    `query` is a JSON rule group:

        {"combinator": "and", "rules": [
           {"property": "$blueprint", "operator": "=",  "value": "STORY"},
           {"property": "state",      "operator": "!=", "value": "Done"}]}

    Properties are either `$`-prefixed meta-properties (`$title`,
    `$blueprint`, `$source`, `$path`, `$identifier`, `$createdAt`,
    `$updatedAt`, `$syncedAt`) or a bare attribute key from
    `describe_schema`. Operators: `=`, `!=`, `contains`, `doesNotContain`,
    `beginsWith`, `endsWith`, `in`, `notIn`, `containsAny`, `>`, `>=`, `<`,
    `<=`, `between`, `notBetween`, `isEmpty`, `isNotEmpty`.

    Relations traverse the graph:

        {"relation": "VERIFIES", "operator": "relatedTo", "value": "324",
         "direction": "upstream", "maxHops": 1}

    `notRelatedTo` answers the "what's missing" questions — stories with no
    test coverage, repos with no owning team.

    Returns a shared `nodes` dictionary (each node appears once, referenced by
    short id), `anchors` pointing into it, semantic `edges` as triples, and a
    `rollup` of counts across the whole match set. Hierarchy is carried by each
    node's `path` rather than as edges. Anchors carry a `locator` for handing
    off to the vendor's own MCP server.
    """
    request = EntityQuery(query=_parse_rule_group(query), limit=limit)
    async with session_scope() as session:
        result = await search_entities(request, session=session)
    return json.dumps(result, default=str)


async def aggregate_entities_tool(
    query: str, group_by: list[str], metrics: str | None = None
) -> str:
    """Group entities and compute a metric per group — count by default.

    Same rule grammar as `search_entities` for the filter; `group_by` names
    properties to group on (`$source`, `$blueprint`, `state`, ...). Use this
    instead of fetching rows and computing something over them yourself —
    "how many open PRs per repository" or "average PR cycle time per repo"
    is one call, not N.

    `metrics` is an optional JSON array of metric specs, each
    `{"op": ..., "property": ...}` or, for a duration,
    `{"op": "avg_duration_days", "start": ..., "end": ...}`. Ops: `count`
    (default, needs nothing else), `avg`, `sum`, `min`, `max` (need
    `property`), `avg_duration_days` (needs `start` and `end` — the metric
    that answers "average PR cycle time", which a plain avg can't express
    since it's an interval between two properties, not one column). Add
    `"as": "name"` to any spec to control its key in the response.

        metrics='[{"op":"avg_duration_days","start":"created_at","end":"closed_at","as":"cycle_time_days"}]'

    Computed live from the database, so the numbers are never stale.
    """
    metric_specs = json.loads(metrics) if metrics else None
    request = AggregateQuery(
        query=_parse_rule_group(query),
        group_by=group_by,
        **({"metrics": metric_specs} if metric_specs is not None else {}),
    )
    async with session_scope() as session:
        result = await aggregate_entities(request, session=session)
    return json.dumps(result, default=str)
