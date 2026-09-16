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
from uuid import UUID

from context_fabric.api.routes.catalog import (
    aggregate_entities,
    describe_schema,
    locator_json,
    search_entities,
)
from context_fabric.domain.query import AggregateQuery, EntityQuery, RuleGroup
from context_fabric.persistence.repositories.context_space import ContextSpaceRepository
from context_fabric.persistence.repositories.node import NodeRepository
from context_fabric.persistence.repositories.workflow_template import WorkflowTemplateRepository
from context_fabric.persistence.session import session_scope
from context_fabric.retrieval.scope import resolve_scope


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


async def resolve_scope_tool(
    task_ref: str, actor_id: str, context_space_override: str | None = None
) -> str:
    """Which repo/team/product a task belongs to (docs/RETRIEVAL.md §1).

    Deterministic and model-call-free (ADR-006): given a task_ref (e.g.
    "AB#312", a Jira key, "owner/repo#42", "CONFPAGE-98765"), finds the
    already-synced node it names, walks context-space bindings for the one
    whose boundary contains it, and returns that scope — product, teams,
    services, and `repositories` (this is what a harness should clone).

    This never executes anything — it only tells a harness what's there and
    where. Once scope is resolved, query for what's available to run in that
    scope with `search_entities` (e.g. `{"$blueprint": "AI_ASSET", "$path":
    "beginsWith <a repository's path>"}`) and fetch full agent/skill
    definitions via that connector's own on-demand content locator.

    A task_ref that can't be parsed, was never synced, or has no covering
    context-space binding comes back as `resolved: false` with a `reason` —
    never an exception, never a silent empty success.

    Args:
        task_ref: e.g. "AB#312", "TALENT-42", "acme-org/repo#7", "CONFPAGE-123".
        actor_id: identity of the caller (authorization isn't wired in yet —
            this is a pass-through seam, see retrieval/scope.py).
        context_space_override: optional, restrict resolution to one
            already-known context space instead of searching all of them.
    """
    async with session_scope() as session:
        node_repo = NodeRepository(session)
        context_space_repo = ContextSpaceRepository(session)
        result = await resolve_scope(
            node_repo,
            context_space_repo,
            task_ref,
            actor_id,
            context_space_override=context_space_override,
        )
    return result.model_dump_json()


async def list_workflow_templates_tool(context_space_id: str | None = None) -> str:
    """Discover workflow templates — a named, ordered pipeline of steps
    (each a specific agent/skill) a harness pulls and executes in order.
    Context Fabric only stores and serves templates; it never runs one.

    Lightweight on purpose (no per-step locator resolution — that's what
    `get_workflow_template` is for): use this to find a template's id,
    then fetch the full pipeline with `get_workflow_template`. The
    natural harness flow is `resolve_scope(task_ref)` ->
    `list_workflow_templates(context_space_id)` ->
    `get_workflow_template(id)`.

    Args:
        context_space_id: optional, restrict to templates authored
            against one context space (e.g. the one `resolve_scope` just
            returned).
    """
    async with session_scope() as session:
        template_repo = WorkflowTemplateRepository(session)
        templates = await template_repo.list_all(context_space_id)
        result = [
            {
                "id": str(t.id),
                "context_space_id": t.context_space_id,
                "name": t.name,
                "description": t.description,
                "status": t.status,
                "step_count": len(t.steps),
            }
            for t in templates
        ]
    return json.dumps(result, default=str)


async def get_workflow_template_tool(template_id: str) -> str:
    """Fetch one workflow template's full, ordered pipeline of steps —
    each step a specific agent/skill picked from the catalog at author
    time, with a `locator` resolved fresh (right now, not from the
    template's own snapshot) so a harness knows exactly how to fetch the
    step's full definition via that vendor's own MCP server.

    A step whose underlying node no longer resolves (the repo was
    unsynced, the file was removed) comes back with `resolved: false` and
    `locator: null` rather than a stale or fabricated locator — the
    template's own display fields (`label`/`vendor`/`asset_type`) still
    show, same reconcile-style distinction `resolve_scope`'s candidates
    and `reconcile_context_space` already make elsewhere.

    Context Fabric never executes a step — this tool only tells a harness
    what the pipeline is and where each step's definition lives.

    Args:
        template_id: the workflow template's id (from
            `list_workflow_templates` or the UI).
    """
    async with session_scope() as session:
        template_repo = WorkflowTemplateRepository(session)
        node_repo = NodeRepository(session)
        template = await template_repo.get(UUID(template_id))
        if template is None:
            return json.dumps(
                {"resolved": False, "reason": f"no workflow template with id={template_id!r}"}
            )

        steps = []
        for step in template.steps:
            node = await node_repo.get_by_technical_identity(
                step.source_system, step.source_instance_id, step.native_id
            )
            steps.append(
                {
                    "id": str(step.id),
                    "order": step.order,
                    "label": step.label,
                    "vendor": step.vendor,
                    "asset_type": step.asset_type,
                    "instructions": step.instructions,
                    "resolved": node is not None,
                    "locator": locator_json(node) if node is not None else None,
                }
            )
        result = {
            "id": str(template.id),
            "context_space_id": template.context_space_id,
            "name": template.name,
            "description": template.description,
            "status": template.status,
            "steps": steps,
        }
    return json.dumps(result, default=str)


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
