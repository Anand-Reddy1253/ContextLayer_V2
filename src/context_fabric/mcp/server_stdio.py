"""Context MCP — stdio transport (docs/MCP.md).

Not the full four-tool spec yet. `resolve_scope` is real (this file
registers it, `retrieval/scope.py` implements it), and so is the
harness-composition pair `list_workflow_templates`/`get_workflow_template`
(`catalog/workflow_templates.py` + `persistence/repositories/
workflow_template.py`) — the natural flow being `resolve_scope(task_ref)`
-> `list_workflow_templates(context_space_id)` -> `get_workflow_template(id)`,
handing a harness a fully-locator-resolved, ordered pipeline of steps to
execute. The remaining two, `get_context_pack` and
`expand_evidence`/`refresh_evidence`, still depend on infrastructure that
doesn't exist yet — `configs/stage-contracts.yaml`, an evidence cache with
token-budget enforcement. Building against that before it exists would mean
either stubbing those pieces (fake data, exactly what this session has
spent its effort *removing* from the demo) or blocking on a much larger
build.

What's real and already tested is `catalog.search_cards` — the same
logic backing `GET /api/catalog/search-cards`, verified this session
against live Azure DevOps/GitHub/Confluence data. `search_context`
(`mcp/tools.py`) calls that same function directly (not over HTTP) so
there's no extra hop, then trims the result for this transport — the
matched node still carries its full `locator.native_call`, but its
`ancestors`/`links` (breadcrumbs and cross-references, not the match
itself) are cut to essentials, since a full duplicate node record per
ancestor/link, unbounded, was found live to dominate response size (one
card: 33KB, 31KB of it `links`) for data nothing downstream reads at
that depth. The point of this being an MCP tool instead of a REST curl
target is that an agent can call it inline in its own tool loop, get
back the exact vendor tool + params for follow-up, and hand off to the
real native GitHub/ADO/Confluence MCP tools for full content (ADR-003 —
this server is the map, never a data replica).

Run standalone: `python -m context_fabric.mcp.server_stdio`
Actor identity: none yet — authorization/RBAC (ADR-007) isn't wired
into this endpoint, same gap as the REST API today. Do not point this
at anything multi-tenant until that's built.
"""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer

from context_fabric.mcp import tools

mcp = MCPServer("context-fabric")


# Implementations live in mcp/tools.py so an HTTP transport can register the
# same ones (docs/MCP.md). The decorator reads the signature and docstring at
# registration time — those *are* the schema and description the model sees, so
# they belong here rather than being copied across afterwards.
#
# structured_output=False on every tool below: every one already returns its
# own pre-serialized JSON string (mcp/tools.py's own docstring — "each
# returns a JSON string because that is what an MCP tool result is"). Left at
# the SDK's default, a bare `-> str` return annotation still triggers
# "structured output" support, which wraps that already-JSON string a second
# time as `{"result": "<the same string, now fully quote-escaped>"}` *and*
# sends it *in addition to* the identical plain-text content block — every
# call ships its payload twice, and the wrapped copy is bigger than the
# original because of the escaping. Found live: describe_schema() sent 5,021
# chars of text plus a second, 5,793-char structured copy of the exact same
# data, advertised under a schema of `{"result": {"type": "string"}}` that
# tells a caller nothing. structured_output=False turns all of that off —
# one copy, no synthetic wrapper — with no change to what any tool returns.
@mcp.tool(structured_output=False)
async def resolve_scope(
    task_ref: str, actor_id: str, context_space_override: str | None = None
) -> str:
    """Which repo/team/product a task belongs to (docs/RETRIEVAL.md §1).

    Deterministic and model-call-free: given a task_ref (e.g. "AB#312", a
    Jira key like "TALENT-42", "owner/repo#42", or "CONFPAGE-98765"), finds
    the already-synced node it names, walks context-space bindings for the
    one whose boundary contains it, and returns that scope — product,
    teams, services, and `repositories` (what a harness should clone).

    This tool never executes anything — it only tells a harness what's
    there and where. Once scope is resolved, query for what's available to
    run in that scope with search_entities (e.g. {"$blueprint": "AI_ASSET",
    "$path": "beginsWith <a repository's path>"}) and fetch the full
    agent/skill definition via that connector's own on-demand content
    locator.

    A task_ref that can't be parsed, was never synced, or has no covering
    context-space binding comes back as resolved: false with a reason —
    never an exception, never a silent empty success.

    Args:
        task_ref: e.g. "AB#312", "TALENT-42", "acme-org/repo#7", "CONFPAGE-123".
        actor_id: identity of the caller (authorization isn't wired in yet).
        context_space_override: optional, restrict resolution to one
            already-known context space instead of searching all of them.
    """
    return await tools.resolve_scope_tool(task_ref, actor_id, context_space_override)


@mcp.tool(structured_output=False)
async def list_workflow_templates(context_space_id: str | None = None) -> str:
    """Discover workflow templates — a named, ordered pipeline of steps
    (each a specific agent/skill) a harness pulls and executes in order.
    Context Fabric only stores and serves templates; it never runs one.

    Lightweight on purpose (no per-step locator resolution — that's what
    get_workflow_template is for): use this to find a template's id, then
    fetch the full pipeline with get_workflow_template. The natural
    harness flow is resolve_scope(task_ref) ->
    list_workflow_templates(context_space_id) -> get_workflow_template(id).

    Args:
        context_space_id: optional, restrict to templates authored
            against one context space (e.g. the one resolve_scope just
            returned).
    """
    return await tools.list_workflow_templates_tool(context_space_id)


@mcp.tool(structured_output=False)
async def get_workflow_template(template_id: str) -> str:
    """Fetch one workflow template's full, ordered pipeline of steps —
    each step a specific agent/skill picked from the catalog at author
    time, with a locator resolved fresh (right now, not from the
    template's own snapshot) so a harness knows exactly how to fetch the
    step's full definition via that vendor's own MCP server.

    A step whose underlying node no longer resolves (the repo was
    unsynced, the file was removed) comes back with resolved: false and
    locator: null rather than a stale or fabricated locator — the
    template's own display fields (label/vendor/asset_type) still show.

    Context Fabric never executes a step — this tool only tells a harness
    what the pipeline is and where each step's definition lives.

    Args:
        template_id: the workflow template's id (from
            list_workflow_templates or the UI).
    """
    return await tools.get_workflow_template_tool(template_id)


@mcp.tool(structured_output=False)
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


@mcp.tool(structured_output=False)
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

    A `warnings` key appears only when `rollup.matched` is 0 AND the query
    named a `$blueprint` (kind) that doesn't exist at all, or doesn't exist
    for the `$source` it was paired with — e.g. `$blueprint="BUG"` against
    `$source="github"` (GitHub has no BUG kind; "bug" is only ever a label
    on an ISSUE there, while Jira *does* have a real BUG kind). Without this,
    a wrong kind name and a genuinely-empty result look identical. A bare
    `matched: 0` with no `warnings` key means the zero is real — call
    describe_schema first if unsure which kinds exist per source.

    Args:
        query: the JSON rule group.
        limit: max anchors to return (default 25).
    """
    return await tools.search_entities_tool(query, limit)


@mcp.tool(structured_output=False)
async def aggregate_entities(
    query: str, group_by: list[str], metrics: str | None = None
) -> str:
    """Group entities and compute a metric per group — count by default.

    Same rule grammar as search_entities for the filter. Use this instead of
    fetching rows and computing something yourself — "how many open PRs per
    repository" or "average PR cycle time per repo" is one call, not N.
    Computed live, so never stale.

    Returns `{"results": [...], "warnings": [...]}` — `warnings` is always
    present (possibly empty) so an empty `results` is never silently
    ambiguous between "genuinely zero groups" and "the query's own
    `$blueprint` premise doesn't apply to the `$source` it was grouped/
    filtered by" (same trap as search_entities — see its own docstring).

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


@mcp.tool(structured_output=False)
async def search_context(
    q: str,
    business_node_id: str | None = None,
    limit: int = 10,
    include_links: bool = False,
) -> str:
    """Search Context Fabric's technical catalog (Azure DevOps work
    items/builds/pipelines, GitHub repos/PRs, Confluence pages) for a
    topic and return matching "cards": each match's ancestor chain
    (containment — the project/repo/space it lives in), its owning
    team/business context, and a `locator.native_call` giving the exact
    vendor MCP tool + params to fetch full content from the real source.
    `ancestors` are trimmed to kind/name/native_id — a breadcrumb, not a
    fetch target — see `search_context_tool`'s own docstring for the
    exact shape and why.

    Cross-system `links` are left out by default — they were the single
    biggest cost driver of every response, and most searches don't need
    them for every result. Set `include_links=true` to get them inline
    anyway, or (usually cheaper) once you know which result you care
    about, call `search_entities` with a relation clause against that
    result's own `locator.native_id` instead — one call, scoped to just
    that node, with real relation-query power (multi-hop, `notRelatedTo`)
    inline links can't offer.

    Args:
        q: search term (matched against node name/description).
        business_node_id: optional UUID to scope results to one
            team/business unit's context space (see the Enterprise
            Graph / org tree for available team ids).
        limit: max cards to return (default 10).
        include_links: include each result's cross-system links inline
            (default False).
    """
    return await tools.search_context_tool(q, business_node_id, limit, include_links)


if __name__ == "__main__":
    mcp.run(transport="stdio")
