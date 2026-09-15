"""Catalog (technical layer) — docs/API.md "Catalog". Mostly read-only
(the graph is sync-owned), with one deliberate exception: a human can
manually assert a relationship between two technical nodes that no
regex could ever find (docs/UI.md "Catalog Explorer" — e.g. "this
Confluence page documents that repo") via POST .../links, and remove one
via DELETE /edges/{id}. Both operate only on origin=HUMAN territory —
nothing here ever touches a sync-owned or extracted edge."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from context_fabric.api.deps import get_session
from context_fabric.domain.edge import Edge
from context_fabric.domain.enums import EdgeOrigin, EdgeState, EdgeType, Layer
from context_fabric.domain.query import AggregateQuery, EntityQuery
from context_fabric.persistence.orm.edge import EdgeORM
from context_fabric.persistence.orm.node import NodeORM
from context_fabric.persistence.repositories.context_space import ContextSpaceRepository
from context_fabric.persistence.repositories.edge import EdgeRepository
from context_fabric.persistence.repositories.node import NodeRepository
from context_fabric.retrieval.query_compiler import (
    QueryError,
    compile_group,
    resolve_relations,
)

router = APIRouter(prefix="/api/catalog", tags=["catalog"])


def _node_json(node: Any) -> dict[str, Any]:
    return {
        "id": str(node.id),
        "layer": node.layer.value,
        "kind": node.kind,
        "capability": node.capability.value if node.capability else None,
        "name": node.name,
        "description": node.description,
        "source_system": node.source_system,
        "source_instance_id": node.source_instance_id,
        "native_id": node.native_id,
        "parent_id": str(node.parent_id) if node.parent_id else None,
        "path": node.path,
        "status": node.status.value,
        "deleted_at": node.deleted_at.isoformat() if node.deleted_at else None,
        "attributes": node.attributes,
    }


def _edge_json(edge: Any) -> dict[str, Any]:
    return {
        "id": str(edge.id),
        "src_id": str(edge.src_id),
        "dst_id": str(edge.dst_id),
        "type": edge.type.value,
        "origin": edge.origin.value,
        "state": edge.state.value,
        "confidence": edge.confidence,
        "evidence": (edge.attributes or {}).get("evidence"),
    }


def _native_call_json(node: Any) -> dict[str, Any] | None:
    """The exact tool name + params a *native* per-vendor MCP server would
    need to fetch this object directly — distinct from `url`, which is
    for a human. Researched against each vendor's real, current MCP
    server (docs/BENCHMARK.md): GitHub's `get_file_contents` wants
    `{owner, repo, path, ref}`, not a URL; Azure DevOps's
    `wit_get_work_items_batch` wants `{project, ids}`, where `project`
    can be the project GUID already embedded in the node's own stored
    `url` (the path segment right after the org hostname) — no extra
    connector-side lookup needed. Returns None for kinds with no
    single-object native fetch that matters (e.g. a bare repository or
    project container) rather than guessing.
    """
    system = node.source_system
    kind = node.kind
    native_id = node.native_id
    attrs = node.attributes or {}
    url = attrs.get("url") or ""

    if system == "azure_devops":
        segments = urlsplit(url).path.strip("/").split("/")
        project = segments[0] if segments and segments[0] else None
        if project is None or native_id is None:
            return None
        return {
            "tool": "wit_get_work_items_batch",
            "params": {"project": project, "ids": [native_id]},
        }

    if system == "github" and native_id is not None:
        if kind == "PULL_REQUEST":
            repo, _, number = native_id.rpartition("#")
            owner, _, name = repo.partition("/")
            if number.isdigit():
                return {
                    "tool": "get_pull_request",
                    "params": {"owner": owner, "repo": name, "pullNumber": int(number)},
                }
        if kind == "ISSUE":
            repo, _, number = native_id.rpartition("#")
            owner, _, name = repo.partition("/")
            if number.isdigit():
                return {
                    "tool": "get_issue",
                    "params": {"owner": owner, "repo": name, "issue_number": int(number)},
                }
        if kind in ("FILE", "DIRECTORY"):
            repo_branch, sep, path = native_id.partition(":")
            repo, _, branch = repo_branch.partition("@")
            owner, _, name = repo.partition("/")
            if sep:
                return {
                    "tool": "get_file_contents",
                    "params": {"owner": owner, "repo": name, "path": path, "ref": branch},
                }
        return None

    if system == "confluence" and kind == "PAGE" and native_id is not None:
        return {"tool": "getConfluencePage", "params": {"pageId": native_id}}

    if system == "jira" and kind != "PROJECT" and native_id is not None:
        return {"tool": "getJiraIssue", "params": {"issueIdOrKey": native_id}}

    if system == "teams" and native_id is not None:
        channel_id = attrs.get("channel_id")
        if channel_id:
            return {
                "tool": "get_channel_messages",
                "params": {"channelId": channel_id, "messageId": native_id},
            }
        return None

    return None


def _locator_json(node: Any) -> dict[str, Any]:
    """Everything a caller needs to identify and fetch this exact object
    from its native source, independent of Context Fabric's own id
    (docs/UI.md "Search") — a downstream agent handing this off to a
    native per-vendor MCP server (GitHub's own, Atlassian's, ...) needs
    the source system, its native identity, and a fully-qualified deep
    link, not our internal UUID. `url` already encodes the org/site
    context (e.g. "https://acme.atlassian.net/browse/TALENT-2"), so no
    separate connection-config lookup is needed here. `native_call`
    additionally gives the literal tool + params a *native* MCP server
    call would need — found missing via research (docs/BENCHMARK.md):
    a human-readable URL alone isn't the input shape those tools
    actually take."""
    return {
        "source_system": node.source_system,
        "source_instance_id": node.source_instance_id,
        "native_id": node.native_id,
        "kind": node.kind,
        "url": (node.attributes or {}).get("url"),
        "native_call": _native_call_json(node),
    }


@router.get("/nodes/{node_id}")
async def get_node(node_id: UUID, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    node = await NodeRepository(session).get(node_id)
    if node is None:
        raise HTTPException(404, "node not found")
    return _node_json(node)


@router.get("/nodes/{node_id}/children")
async def get_node_children(
    node_id: UUID, session: AsyncSession = Depends(get_session)
) -> list[dict[str, Any]]:
    """Every descendant, not just direct children — the "N descendants"
    count on a container card (docs/UI.md "Catalog Explorer")."""
    node_repo = NodeRepository(session)
    node = await node_repo.get(node_id)
    if node is None:
        raise HTTPException(404, "node not found")
    descendants = await node_repo.list_descendants(node.path, include_self=False)
    return [_node_json(n) for n in descendants]


@router.get("/nodes/{node_id}/direct-children")
async def get_node_direct_children(
    node_id: UUID, session: AsyncSession = Depends(get_session)
) -> list[dict[str, Any]]:
    """One level down only — the node detail panel's Hierarchy tab
    (docs/UI.md "Catalog Explorer"), distinct from /children's full
    descendant count."""
    node_repo = NodeRepository(session)
    node = await node_repo.get(node_id)
    if node is None:
        raise HTTPException(404, "node not found")
    children = await node_repo.list_direct_children(node_id)
    return [_node_json(n) for n in children]


@router.get("/nodes/{node_id}/ancestors")
async def get_node_ancestors(
    node_id: UUID, session: AsyncSession = Depends(get_session)
) -> list[dict[str, Any]]:
    """The breadcrumb chain up to the root, excluding the node itself —
    the node detail panel's Hierarchy tab."""
    node_repo = NodeRepository(session)
    node = await node_repo.get(node_id)
    if node is None:
        raise HTTPException(404, "node not found")
    ancestors = await node_repo.list_ancestors_of_path(node.path)
    return [_node_json(n) for n in ancestors if n.id != node_id]


@router.get("/nodes/{node_id}/links")
async def get_node_links(
    node_id: UUID, session: AsyncSession = Depends(get_session)
) -> list[dict[str, Any]]:
    """Non-structural links (MENTIONS/RELATED_TO) touching this node in
    either direction, with the linked node's own summary attached — the
    node detail panel's Hierarchy tab "dependencies" section
    (docs/UI.md "Catalog Explorer"). CONTAINS is excluded; that's the
    structural tree, shown separately as ancestors/children."""
    node_repo = NodeRepository(session)
    node = await node_repo.get(node_id)
    if node is None:
        raise HTTPException(404, "node not found")
    edges = await EdgeRepository(session).list_touching(
        node_id, exclude_types=[EdgeType.CONTAINS.value]
    )
    counterpart_ids = {e.dst_id if e.src_id == node_id else e.src_id for e in edges}
    counterparts = {n.id: n for n in await node_repo.get_many(list(counterpart_ids))}
    results = []
    for e in edges:
        other_id = e.dst_id if e.src_id == node_id else e.src_id
        other = counterparts.get(other_id)
        results.append(
            {
                "edge": _edge_json(e),
                "direction": "outgoing" if e.src_id == node_id else "incoming",
                "node": _node_json(other) if other is not None else None,
            }
        )
    return results


class CreateNodeLinkRequest(BaseModel):
    target_node_id: UUID
    type: EdgeType


@router.post("/nodes/{node_id}/links", status_code=201)
async def create_node_link(
    node_id: UUID, body: CreateNodeLinkRequest, session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    """Manually asserts a relationship between two technical nodes that
    no regex could ever find — e.g. "this Confluence page documents that
    repo" (docs/UI.md "Catalog Explorer"). origin=HUMAN, state=ACTIVE:
    unlike a SYNC_EXTRACTED guess (always PROPOSED until confirmed), a
    human assertion is trusted immediately."""
    node_repo = NodeRepository(session)
    src = await node_repo.get(node_id)
    if src is None:
        raise HTTPException(404, "node not found")
    dst = await node_repo.get(body.target_node_id)
    if dst is None:
        raise HTTPException(404, "target node not found")
    if src.id == dst.id:
        raise HTTPException(400, "a node cannot be related to itself")

    edge_repo = EdgeRepository(session)
    existing = await edge_repo.get_by_identity(
        node_id, body.target_node_id, body.type.value, EdgeOrigin.HUMAN.value
    )
    if existing is not None:
        raise HTTPException(409, "this relationship already exists")

    now = datetime.now(UTC)
    created = await edge_repo.create(
        Edge(
            src_id=node_id,
            dst_id=body.target_node_id,
            type=body.type,
            origin=EdgeOrigin.HUMAN,
            first_seen_at=now,
            last_seen_at=now,
        )
    )
    return _edge_json(created)


@router.delete("/edges/{edge_id}", status_code=204)
async def delete_edge(edge_id: UUID, session: AsyncSession = Depends(get_session)) -> None:
    """Removes a manually-asserted (or any other) edge — soft-deleted,
    same as a technical node's own tombstone, so it stops appearing in
    list_touching/list_among without a hard row delete."""
    await EdgeRepository(session).soft_delete(edge_id, datetime.now(UTC))


@router.get("/edges/proposed")
async def list_proposed_edges(
    type: str | None = None, session: AsyncSession = Depends(get_session)
) -> list[dict[str, Any]]:
    """The review queue documented in docs/UI.md "Proposed links review
    queue" — every `state=PROPOSED` edge (produced today by
    synchronization/link_extraction.py's regex-based extraction), each
    with its src/dst node summaries resolved so the UI never has to make
    a second round trip per row. `type` optionally narrows to a
    comma-separated list of EdgeType values (e.g. "RELATED_TO,MENTIONS")."""
    edge_types = type.split(",") if type else None
    edges = await EdgeRepository(session).list_by_state("PROPOSED", edge_types=edge_types)
    node_repo = NodeRepository(session)
    result = []
    for edge in edges:
        src = await node_repo.get(edge.src_id)
        dst = await node_repo.get(edge.dst_id)
        result.append(
            {
                "edge": _edge_json(edge),
                "src": _node_json(src) if src else None,
                "dst": _node_json(dst) if dst else None,
            }
        )
    return result


@router.post("/edges/{edge_id}/confirm")
async def confirm_proposed_edge(
    edge_id: UUID, session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    """A human agrees the extracted relationship is real — PROPOSED ->
    ACTIVE, docs/UI.md "Proposed links review queue"."""
    edge_repo = EdgeRepository(session)
    edge = await edge_repo.get(edge_id)
    if edge is None:
        raise HTTPException(404, "edge not found")
    updated = await edge_repo.set_state(edge_id, EdgeState.ACTIVE.value, datetime.now(UTC))
    return _edge_json(updated)


@router.post("/edges/{edge_id}/reject")
async def reject_proposed_edge(
    edge_id: UUID, session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    """A human decides the extracted relationship is wrong — PROPOSED ->
    REJECTED. Kept as a row (not deleted) so the same regex match doesn't
    resurface as a fresh proposal on the next sync — idempotency.py's
    upsert_edge matches on (src, dst, type, origin), so a REJECTED row
    with that identity blocks re-proposal rather than needing separate
    suppression bookkeeping."""
    edge_repo = EdgeRepository(session)
    edge = await edge_repo.get(edge_id)
    if edge is None:
        raise HTTPException(404, "edge not found")
    updated = await edge_repo.set_state(edge_id, EdgeState.REJECTED.value, datetime.now(UTC))
    return _edge_json(updated)


class RetypeProposedEdgeRequest(BaseModel):
    dst_node_id: UUID


@router.post("/edges/{edge_id}/retype")
async def retype_proposed_edge(
    edge_id: UUID, body: RetypeProposedEdgeRequest, session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    """A human confirms the relationship is real but the proposed target
    was wrong (e.g. an ambiguous match) — points the edge at a different
    node and confirms it in one step, rather than reject-then-manually-
    recreate."""
    edge_repo = EdgeRepository(session)
    edge = await edge_repo.get(edge_id)
    if edge is None:
        raise HTTPException(404, "edge not found")
    node_repo = NodeRepository(session)
    target = await node_repo.get(body.dst_node_id)
    if target is None:
        raise HTTPException(404, "target node not found")
    updated = await edge_repo.retype_dst(edge_id, body.dst_node_id, datetime.now(UTC))
    return _edge_json(updated)


@router.get("/nodes/{node_id}/graph")
async def get_node_graph(
    node_id: UUID, session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    """The full subgraph rooted at this node — every descendant plus
    every edge (structural and extracted) among them — for the "complete
    graph" view on a top-level container (docs/UI.md "Catalog Explorer").
    An edge to something outside this subtree never appears, so the
    rendered graph is always self-contained."""
    node_repo = NodeRepository(session)
    node = await node_repo.get(node_id)
    if node is None:
        raise HTTPException(404, "node not found")
    nodes = await node_repo.list_descendants(node.path, include_self=True)
    node_ids = [n.id for n in nodes]
    edges = await EdgeRepository(session).list_among(node_ids)
    return {"nodes": [_node_json(n) for n in nodes], "edges": [_edge_json(e) for e in edges]}


async def _build_enterprise_graph_data(
    session: AsyncSession,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Shared by GET /enterprise-graph and GET /search-cards' business-node
    scoping — both need the same whole-graph-with-synthesized-LOGICAL-layer
    shape, the latter purely to BFS over it server-side (docs/UI.md
    "Search"), so this is the one place that assembly happens."""
    node_repo = NodeRepository(session)
    edge_repo = EdgeRepository(session)
    context_space_repo = ContextSpaceRepository(session)

    business_nodes = await node_repo.list_by_layer(Layer.BUSINESS)
    technical_nodes = await node_repo.list_by_layer(Layer.TECHNICAL)
    real_node_ids = [n.id for n in business_nodes] + [n.id for n in technical_nodes]
    real_edges = await edge_repo.list_among(real_node_ids)

    nodes: list[dict[str, Any]] = [_node_json(n) for n in business_nodes] + [
        _node_json(n) for n in technical_nodes
    ]
    edges: list[dict[str, Any]] = [_edge_json(e) for e in real_edges]

    for n in business_nodes:
        if n.parent_id is not None:
            edges.append(
                {
                    "id": f"biz-parent:{n.id}",
                    "src_id": str(n.parent_id),
                    "dst_id": str(n.id),
                    "type": "CONTAINS",
                    "origin": "HUMAN",
                    "state": "ACTIVE",
                    "confidence": None,
                }
            )

    for space in await context_space_repo.list_all():
        virtual_id = f"ctxspace:{space.id}"
        nodes.append(
            {
                "id": virtual_id,
                "layer": "LOGICAL",
                "kind": "CONTEXT_SPACE",
                "capability": None,
                "name": space.name,
                "description": space.description,
                "source_system": None,
                "source_instance_id": None,
                "native_id": space.id,
                "parent_id": str(space.business_node_id),
                "path": f"ctxspace.{space.id}",
                "status": space.status,
                "deleted_at": None,
                "attributes": {
                    "product": space.product,
                    "teams": space.teams,
                    "services": space.services,
                },
            }
        )
        edges.append(
            {
                "id": f"biz-ctxspace:{space.id}",
                "src_id": str(space.business_node_id),
                "dst_id": virtual_id,
                "type": "HAS_CONTEXT_SPACE",
                "origin": "HUMAN",
                "state": "ACTIVE",
                "confidence": None,
            }
        )
        for binding in space.bindings:
            target = await node_repo.get_by_technical_identity(
                binding.source_system, binding.source_instance_id, binding.native_container
            )
            if target is None:
                continue
            edges.append(
                {
                    "id": f"binding:{binding.id}",
                    "src_id": virtual_id,
                    "dst_id": str(target.id),
                    "type": "BINDS",
                    "origin": binding.origin.value,
                    "state": "ACTIVE",
                    "confidence": None,
                    # Carried through so scoped views (team filter on
                    # Asset Catalog/Enterprise Graph) can exclude
                    # capabilities that are shared across every team bound
                    # to the same container (WORK_MANAGEMENT on a shared
                    # ADO project, confirmed this session to be 81% of the
                    # whole graph) — without this, "scope to my team"
                    # degenerates into "scope to whatever's shared."
                    "capability": binding.capability.value,
                }
            )

    return nodes, edges


@router.get("/enterprise-graph")
async def get_enterprise_graph(session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    """The whole graph in one shot — every BUSINESS node, every TECHNICAL
    node, and the LOGICAL layer connecting them (docs/UI.md "Enterprise
    Context Graph"). ContextSpace/Binding are synthesized into graph
    nodes/edges here since neither is a `node`/`edge` table row; business
    hierarchy is likewise synthesized from `parent_id` — business-tree
    seeding never creates Edge rows the way sync's structural CONTAINS
    does. Every synthetic id is prefixed (`ctxspace:`, `biz-parent:`,
    `biz-ctxspace:`, `binding:`) so it can never collide with a real
    node/edge UUID."""
    nodes, edges = await _build_enterprise_graph_data(session)
    return {"nodes": nodes, "edges": edges}


# Edge types that define "administratively part of this team's scope":
# business hierarchy (CONTAINS between business nodes), a team's own
# context space (HAS_CONTEXT_SPACE), what that space binds (BINDS), and
# a bound container's own structural contents (CONTAINS between technical
# nodes — e.g. a bound repo's own PRs/files). Deliberately excludes
# MENTIONS/RELATED_TO/VERIFIES/DEPENDS_ON (SYNC_EXTRACTED, low-confidence
# guesses, docs/architecture.md "Actual lineage vs. structural
# containment") — those bridge into unrelated parts of the graph through
# a single incidental cross-reference (found via testing: from one real
# team, transitively following every edge type reached 469 of ~476 total
# nodes — scope by that definition means almost nothing).
_SCOPE_EXPANSION_EDGE_TYPES = {"CONTAINS", "HAS_CONTEXT_SPACE", "BINDS"}

# Which capability a technical node's own *kind* represents, independent of
# which BINDS edge happened to reach it. Needed because a single shared
# container can legitimately carry more than one capability binding at once
# (found via a real case: one Azure DevOps project is bound both CODE, for
# its git repos, and WORK_MANAGEMENT, for its boards — same project node,
# two separate Binding rows) — excluding WORK_MANAGEMENT BINDS edges alone
# still leaves the project reachable via its surviving CODE binding, and
# since technical CONTAINS is undirected (deliberately, so a bound
# container's structural contents come along for free), that one surviving
# path re-admits every child regardless of kind, work items included. This
# mapping is the second, kind-based filter that actually separates them.
_KIND_CAPABILITY = {
    "STORY": "WORK_MANAGEMENT",
    "TASK": "WORK_MANAGEMENT",
    "BUG": "WORK_MANAGEMENT",
    "FEATURE": "WORK_MANAGEMENT",
    "TEST_CASE": "WORK_MANAGEMENT",
    "TEST_SUITE": "WORK_MANAGEMENT",
    "TEST_PLAN": "WORK_MANAGEMENT",
    "WORK_ITEM": "WORK_MANAGEMENT",
    "ISSUE": "WORK_MANAGEMENT",
    "PULL_REQUEST": "CODE",
    "BUILD": "CODE",
    "PIPELINE": "CODE",
    "GIT_REPOSITORY": "CODE",
    "REPOSITORY": "CODE",
    "PAGE": "DOCUMENTATION",
    "ATTACHMENT": "DOCUMENTATION",
    "COMMENT": "DOCUMENTATION",
    "AI_ASSET": "DOCUMENTATION",
}


def _reachable_ids(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    root_id: str,
    *,
    edge_types: set[str] | None = _SCOPE_EXPANSION_EDGE_TYPES,
    exclude_capabilities: set[str] | None = None,
) -> set[str]:
    """Every node reachable from `root_id` treating edges as undirected,
    restricted to `edge_types` (None means "any type" — used by the
    Enterprise Graph page's own "scope to node" view, where showing too
    much is a minor annoyance; the default restriction is for anything
    that actually needs to *exclude* results, like search).

    `exclude_capabilities`, when given, additionally drops BINDS edges
    whose binding capability is in the set — a capability like
    WORK_MANAGEMENT bound to a container every team shares (one Azure
    DevOps project, confirmed this session to hold 81% of the whole
    graph) otherwise makes every team's "scope to me" reach nearly the
    same dominant block, which isn't really scoping to anything. Callers
    that want the unfiltered picture just omit this.

    Business-hierarchy CONTAINS (both ends BUSINESS layer, e.g. TRIBE ->
    TEAM) is deliberately traversed **only downward** (parent to child),
    unlike every other edge here — a real bug found via a user report:
    treating it as undirected let scoping to one team walk *up* to its
    parent TRIBE and back *down* into a sibling team's own bindings,
    pulling in that sibling's entire technical subtree regardless of any
    capability exclusion. Technical-layer CONTAINS (a bound container's
    own structural contents) stays undirected as before — that expansion
    is the intended "everything under what I'm bound to," not a leak.

    `exclude_capabilities` also drops technical nodes whose own *kind*
    (`_KIND_CAPABILITY`) maps to an excluded capability, after BFS —
    dropping the BINDS edge alone isn't enough when the same shared
    container carries a second, non-excluded capability binding too (see
    `_KIND_CAPABILITY`'s docstring)."""
    node_layer_by_id = {n["id"]: n.get("layer") for n in nodes}
    node_kind_by_id = {n["id"]: n.get("kind") for n in nodes}
    neighbors: dict[str, list[str]] = {}
    for e in edges:
        if edge_types is not None and e["type"] not in edge_types:
            continue
        if (
            exclude_capabilities is not None
            and e["type"] == "BINDS"
            and e.get("capability") in exclude_capabilities
        ):
            continue
        is_business_hierarchy = (
            e["type"] == "CONTAINS"
            and node_layer_by_id.get(e["src_id"]) == "BUSINESS"
            and node_layer_by_id.get(e["dst_id"]) == "BUSINESS"
        )
        neighbors.setdefault(e["src_id"], []).append(e["dst_id"])
        if not is_business_hierarchy:
            neighbors.setdefault(e["dst_id"], []).append(e["src_id"])

    reachable = {root_id}
    queue = [root_id]
    while queue:
        current = queue.pop(0)
        for nxt in neighbors.get(current, []):
            if nxt not in reachable:
                reachable.add(nxt)
                queue.append(nxt)
    if exclude_capabilities is not None:
        reachable = {
            nid
            for nid in reachable
            if _KIND_CAPABILITY.get(node_kind_by_id.get(nid) or "") not in exclude_capabilities
        }
    return reachable


def _business_context_for(
    candidate_ids: list[str],
    *,
    bind_target_to_ctxspace: dict[str, str],
    ctxspace_to_business: dict[str, str],
    business_node_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    """Checks `candidate_ids` in order (self, nearest ancestor, ..., root)
    for a direct BINDS target — a binding is usually set on a container
    (a whole repo or project), not every individual work item beneath it,
    so a work item's own business context comes from whichever ancestor
    is actually bound, not necessarily itself. This is how a business
    node's "business context" attributes actually reach an agent: not by
    walking the ltree ancestor chain (business nodes aren't in a
    technical node's own hierarchy), but by walking the same
    BINDS/HAS_CONTEXT_SPACE edges the scope filter uses (docs/UI.md
    "Business Hierarchy")."""
    for node_id_str in candidate_ids:
        ctxspace_id = bind_target_to_ctxspace.get(node_id_str)
        if ctxspace_id is None:
            continue
        business_id = ctxspace_to_business.get(ctxspace_id)
        if business_id is None:
            continue
        business_node = business_node_by_id.get(business_id)
        if business_node is None:
            continue
        return {
            "business_node_id": business_id,
            "business_node_name": business_node["name"],
            "attributes": business_node["attributes"],
        }
    return None


def _score_match(q: str, node: Any) -> float | None:
    """Keyword relevance over name/description — `None` means no match.
    Deliberately isolated behind this one function: the plan is to swap
    this for embeddings-based semantic matching over the same two short
    fields later (title + description), without touching anything else
    in /search-cards (docs/UI.md "Search")."""
    ql = q.lower()
    name = (node.name or "").lower()
    if name == ql:
        return 1.0
    if name.startswith(ql):
        return 0.9
    if ql in name:
        return 0.7
    description = (node.description or "").lower()
    if description and ql in description:
        return 0.4
    return None


@router.get("/search-cards")
async def search_cards(
    q: str,
    business_node_id: UUID | None = None,
    exclude_capabilities: str | None = None,
    limit: int = 20,
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    """Topic search over TECHNICAL nodes, returning "cards": the matched
    node, its ancestor chain (containment hierarchy — the repo/project/org
    it lives under), and its direct cross-system links in both directions
    (a PR mentioning a work item, a doc mentioning a repo, ...) — so one
    card shows how a topic touches every source it spans, not just one
    matching node in isolation (docs/UI.md "Search").

    Every node in the response — the match, its ancestors, its linked
    nodes — carries a `locator` (source_system/native_id/url) so a caller
    can hand any one of them off to a native per-vendor MCP server for a
    full read, without going through Context Fabric's own connectors
    (a deliberate departure from docs/MCP.md's "one Context MCP server"
    design for `expand_evidence` — this endpoint is a discovery/search
    surface, not that tool).

    `business_node_id`, when given, restricts results to technical nodes
    reachable from that business node's own context space bindings (and
    anything those transitively relate to) — "search only within my
    team/squad" — computed with the same undirected-BFS semantics as the
    Enterprise Graph page's scope filter, just run server-side so it
    actually excludes rows rather than only highlighting them.

    Ranking is keyword/name+description matching for now
    (`_score_match`) — a placeholder for embeddings-based semantic search
    over the same short fields, planned as a later upgrade.

    Each card also carries `business_context`, when the matched node is
    reachable from exactly one business node's own context space bindings
    — the anchoring business node's name plus its "business context"
    attributes (criticality_tier, compliance_scope, stakeholders,
    communication_channel; docs/UI.md "Business Hierarchy"). This is how
    those attributes actually reach an agent: not by walking the ltree
    ancestor chain (business nodes aren't in a technical node's own
    hierarchy), but by walking the same BINDS/HAS_CONTEXT_SPACE edges the
    scope filter above already uses."""
    node_repo = NodeRepository(session)
    edge_repo = EdgeRepository(session)

    graph_nodes, graph_edges = await _build_enterprise_graph_data(session)
    business_node_by_id = {n["id"]: n for n in graph_nodes if n["layer"] == "BUSINESS"}
    ctxspace_to_business = {
        e["dst_id"]: e["src_id"] for e in graph_edges if e["type"] == "HAS_CONTEXT_SPACE"
    }
    bind_target_to_ctxspace = {
        e["dst_id"]: e["src_id"] for e in graph_edges if e["type"] == "BINDS"
    }

    scope_ids: set[str] | None = None
    if business_node_id is not None:
        scope_ids = _reachable_ids(
            graph_nodes,
            graph_edges,
            str(business_node_id),
            exclude_capabilities=set(exclude_capabilities.split(","))
            if exclude_capabilities
            else None,
        )

    stmt = select(NodeORM).where(
        NodeORM.layer == Layer.TECHNICAL.value,
        NodeORM.deleted_at.is_(None),
        (NodeORM.name.ilike(f"%{q}%")) | (NodeORM.description.ilike(f"%{q}%")),
    )
    rows = (await session.execute(stmt)).scalars().all()

    scored: list[tuple[float, Any]] = []
    for row in rows:
        if scope_ids is not None and str(row.id) not in scope_ids:
            continue
        node = await node_repo.get(row.id)
        assert node is not None
        score = _score_match(q, node)
        if score is not None:
            scored.append((score, node))
    scored.sort(key=lambda pair: pair[0], reverse=True)

    cards: list[dict[str, Any]] = []
    for score, node in scored[: max(0, min(limit, 100))]:
        ancestors = await node_repo.list_ancestors_of_path(node.path)
        edges = await edge_repo.list_touching(node.id, exclude_types=[EdgeType.CONTAINS.value])
        counterpart_ids = {e.dst_id if e.src_id == node.id else e.src_id for e in edges}
        counterparts = {n.id: n for n in await node_repo.get_many(list(counterpart_ids))}

        links = []
        for e in edges:
            other_id = e.dst_id if e.src_id == node.id else e.src_id
            other = counterparts.get(other_id)
            if other is None:
                continue
            links.append(
                {
                    "edge": _edge_json(e),
                    "direction": "outgoing" if e.src_id == node.id else "incoming",
                    "node": _node_json(other),
                    "locator": _locator_json(other),
                }
            )

        cards.append(
            {
                "node": _node_json(node),
                "locator": _locator_json(node),
                "score": score,
                "ancestors": [
                    {"node": _node_json(a), "locator": _locator_json(a)}
                    for a in ancestors
                    if a.id != node.id
                ],
                "links": links,
                "business_context": _business_context_for(
                    [str(node.id)]
                    + [str(a.id) for a in reversed(ancestors) if a.id != node.id],
                    bind_target_to_ctxspace=bind_target_to_ctxspace,
                    ctxspace_to_business=ctxspace_to_business,
                    business_node_by_id=business_node_by_id,
                ),
            }
        )

    return cards


@router.get("/kinds")
async def list_kinds(
    source_system: str | None = None, session: AsyncSession = Depends(get_session)
) -> list[str]:
    """Every distinct node kind actually present in the catalog (e.g.
    WORK_ITEM, PULL_REQUEST, WIKI_PAGE) — drives the Catalog Explorer's
    kind filter and the graph view's legend, so the options offered
    always match what's really been synced rather than a hardcoded
    guess that could drift (docs/UI.md "Catalog Explorer")."""
    stmt = select(NodeORM.kind).where(NodeORM.deleted_at.is_(None)).distinct()
    if source_system:
        stmt = stmt.where(NodeORM.source_system == source_system)
    rows = (await session.execute(stmt)).scalars().all()
    return sorted(rows)


@router.get("/kind-counts")
async def kind_counts(
    business_node_id: UUID | None = None,
    exclude_capabilities: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    """(source_system, kind, count) for every technical node — the Asset
    Catalog's persistent source/kind tree's data source (docs/UI.md "Asset
    Catalog"), so tree counts always match what's really synced. Same
    `business_node_id` team-scoping as /search and /search-cards, so
    selecting a team narrows the tree's counts and its instance lists
    together rather than being two filters to keep in sync."""
    scope_ids: set[str] | None = None
    if business_node_id is not None:
        graph_nodes, graph_edges = await _build_enterprise_graph_data(session)
        parsed_exclude = set(exclude_capabilities.split(",")) if exclude_capabilities else None
        scope_ids = _reachable_ids(
            graph_nodes,
            graph_edges,
            str(business_node_id),
            exclude_capabilities=parsed_exclude,
        )

    stmt = (
        # Labelled node_count, not count: SQLAlchemy Row exposes labels as
        # attributes, and a label of "count" collides with the tuple's own
        # .count() method — it resolves to the label at runtime, but only
        # by luck of precedence, and it type-checks as the method.
        select(NodeORM.source_system, NodeORM.kind, func.count().label("node_count"))
        .where(NodeORM.deleted_at.is_(None), NodeORM.layer == Layer.TECHNICAL.value)
        .group_by(NodeORM.source_system, NodeORM.kind)
    )
    if scope_ids is not None:
        # scope_ids includes synthesized non-node ids too (the virtual
        # "ctxspace:..." context-space node BFS passes through on its way
        # to real bound technical nodes) — only real UUIDs correspond to
        # actual `node` rows, so anything else is correctly excluded here,
        # not a shortcut.
        real_ids = []
        for i in scope_ids:
            try:
                real_ids.append(UUID(i))
            except ValueError:
                continue
        stmt = stmt.where(NodeORM.id.in_(real_ids))
    rows = (await session.execute(stmt)).all()
    return [
        {"source_system": r.source_system, "kind": r.kind, "count": r.node_count}
        for r in rows
        if r.node_count > 0
    ]


@router.get("/search")
async def search_nodes(
    q: str | None = None,
    source_system: str | None = None,
    source_instance_id: str | None = None,
    kind: str | None = None,
    layer: str | None = None,
    business_node_id: UUID | None = None,
    exclude_capabilities: str | None = None,
    limit: int = 100,
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    """Also the technical-asset picker's data source (docs/UI.md "Context
    Spaces" — the AddBindingForm browses synced nodes here rather than
    taking a freehand native_container string), and the Asset Catalog's
    tree/instance-list data source.

    `business_node_id`, when given, scopes results to nodes reachable from
    that business node's own context space bindings — same team-scoping
    semantics as /search-cards, reusing the identical `_reachable_ids` BFS
    over the same synthesized graph, so "scope to my team" means the same
    thing on both pages."""
    scope_ids: set[str] | None = None
    if business_node_id is not None:
        graph_nodes, graph_edges = await _build_enterprise_graph_data(session)
        scope_ids = _reachable_ids(
            graph_nodes,
            graph_edges,
            str(business_node_id),
            exclude_capabilities=set(exclude_capabilities.split(","))
            if exclude_capabilities
            else None,
        )

    stmt = select(NodeORM).where(NodeORM.deleted_at.is_(None))
    if q:
        stmt = stmt.where(NodeORM.name.ilike(f"%{q}%"))
    if source_system:
        stmt = stmt.where(NodeORM.source_system == source_system)
    if source_instance_id:
        stmt = stmt.where(NodeORM.source_instance_id == source_instance_id)
    if kind:
        stmt = stmt.where(NodeORM.kind == kind)
    if layer:
        stmt = stmt.where(NodeORM.layer == layer)
    stmt = stmt.order_by(NodeORM.name)
    # Scope filtering happens on the unbounded result set, same order as
    # /search-cards — SQL-limiting before filtering by scope could drop
    # in-scope rows that just happened to sort after out-of-scope ones.
    if scope_ids is None:
        stmt = stmt.limit(min(limit, 500))

    rows = (await session.execute(stmt)).scalars().all()
    if scope_ids is not None:
        rows = [r for r in rows if str(r.id) in scope_ids][: min(limit, 500)]
    node_repo = NodeRepository(session)
    return [_node_json(await node_repo.get(r.id)) for r in rows]


# ---------------------------------------------------------------------------
# Entity query — the structured surface (docs/API.md "Entity query")
# ---------------------------------------------------------------------------

# Attribute keys promoted onto a node in the lean response when present. Kept
# short on purpose: this response is read by an agent paying per token, and the
# full attribute bag is one expand call away.
_SUMMARY_ATTRS = ("state", "status", "result", "priority", "assigned_to", "updated_at")


def _entity_json(row: NodeORM, *, anchor: bool) -> dict[str, Any]:
    """One node in the shared `nodes` dictionary.

    Anchors (the actual matches) carry a full `locator` so a caller can hand
    them straight to the vendor's own MCP server; everything else — ancestors,
    link counterparts — carries only what's needed to recognize it, because
    those are context rather than answers. Measured: embedding a full node per
    link cost 1.83 KB each and made a 10-result search 85 KB.
    """
    attrs = row.attributes or {}
    entry: dict[str, Any] = {"kind": row.kind, "name": row.name, "path": row.path}
    for key in _SUMMARY_ATTRS:
        if attrs.get(key) not in (None, ""):
            entry[key] = attrs[key]
    if anchor:
        entry["locator"] = {
            "source_system": row.source_system,
            "native_id": row.native_id,
            "url": attrs.get("url") or None,
        }
    else:
        entry["src"] = row.source_system
        entry["native_id"] = row.native_id
    return entry


def _rollup(rows: list[NodeORM]) -> dict[str, Any]:
    """Counts over the whole match set.

    Constant-size regardless of how many rows matched, which is what makes a
    vague question ("what's the state of auth work?") answerable without
    returning the rows at all — and unlike truncation it never misrepresents
    how much exists.
    """
    by_kind: dict[str, int] = {}
    by_state: dict[str, int] = {}
    by_source: dict[str, int] = {}
    for row in rows:
        by_kind[row.kind] = by_kind.get(row.kind, 0) + 1
        if row.source_system:
            by_source[row.source_system] = by_source.get(row.source_system, 0) + 1
        state = (row.attributes or {}).get("state") or (row.attributes or {}).get("status")
        if state:
            by_state[str(state)] = by_state.get(str(state), 0) + 1
    out: dict[str, Any] = {"matched": len(rows), "by_kind": by_kind, "by_source": by_source}
    if by_state:
        out["by_state"] = by_state
    return out


@router.post("/entities/search")
async def search_entities(
    request: EntityQuery, session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    """Structured entity search (docs/API.md "Entity query").

    Takes the rule grammar in domain/query.py — combinator + nested rules,
    operators, and `relatedTo` graph traversal — and returns the lean shape:
    a shared `nodes` dictionary with every node appearing exactly once,
    `anchors` referencing into it, semantic `edges` as triples, and a `rollup`.

    Hierarchy is *not* returned as edges: `path` already encodes the full
    ancestor chain, and CONTAINS is 83% of all edges. Sending it would be
    re-sending what `path` already says.
    """
    try:
        relations = await resolve_relations(session, request.query)
        predicate = compile_group(request.query, relations)
    except QueryError as exc:
        raise HTTPException(400, str(exc)) from exc

    stmt = (
        select(NodeORM)
        .where(NodeORM.deleted_at.is_(None), predicate)
        .order_by(NodeORM.name)
        .limit(request.limit)
    )
    anchors = list((await session.execute(stmt)).scalars().all())
    anchor_ids = [a.id for a in anchors]

    nodes: dict[str, NodeORM] = {str(a.id): a for a in anchors}

    # Ancestors, resolved once each rather than per-anchor. The same project
    # node was previously repeated in all 10 cards of a 10-result response.
    ancestor_paths = {
        ".".join(a.path.split(".")[:i])
        for a in anchors
        for i in range(1, len(a.path.split(".")))
    }
    if ancestor_paths:
        anc_stmt = select(NodeORM).where(
            NodeORM.path.in_(ancestor_paths), NodeORM.deleted_at.is_(None)
        )
        for row in (await session.execute(anc_stmt)).scalars().all():
            nodes.setdefault(str(row.id), row)

    # Semantic edges only — all of them. They are sparse by nature (a repo has
    # hundreds of PRs but a handful of "this PR implements that ticket" links),
    # so there is nothing to gain by truncating and real meaning to lose.
    edges: list[dict[str, str]] = []
    if anchor_ids:
        edge_stmt = select(EdgeORM).where(
            EdgeORM.deleted_at.is_(None),
            EdgeORM.type != EdgeType.CONTAINS.value,
            EdgeORM.src_id.in_(anchor_ids) | EdgeORM.dst_id.in_(anchor_ids),
        )
        edge_rows = list((await session.execute(edge_stmt)).scalars().all())
        counterpart_ids = {
            e.dst_id if e.src_id in set(anchor_ids) else e.src_id for e in edge_rows
        } - set(anchor_ids)
        if counterpart_ids:
            cp_stmt = select(NodeORM).where(
                NodeORM.id.in_(counterpart_ids), NodeORM.deleted_at.is_(None)
            )
            for row in (await session.execute(cp_stmt)).scalars().all():
                nodes.setdefault(str(row.id), row)
        edges = [
            {"src": str(e.src_id), "type": e.type, "dst": str(e.dst_id)}
            for e in edge_rows
            if str(e.src_id) in nodes and str(e.dst_id) in nodes
        ]

    # Short refs keep the payload small and make the edge triples readable.
    ref_by_id = {node_id: f"n{i}" for i, node_id in enumerate(nodes, start=1)}
    anchor_id_set = {str(a.id) for a in anchors}

    return {
        "rollup": _rollup(anchors),
        "anchors": [{"ref": ref_by_id[str(a.id)]} for a in anchors],
        "nodes": {
            ref_by_id[node_id]: _entity_json(row, anchor=node_id in anchor_id_set)
            for node_id, row in nodes.items()
        },
        "edges": [
            {"src": ref_by_id[e["src"]], "type": e["type"], "dst": ref_by_id[e["dst"]]}
            for e in edges
        ],
        "expand": {"node": "/api/catalog/nodes/{id}/links"},
    }


@router.post("/entities/aggregate")
async def aggregate_entities(
    request: AggregateQuery, session: AsyncSession = Depends(get_session)
) -> list[dict[str, Any]]:
    """Group-and-count (or avg/min/max/sum/avg_duration_days) over the same
    filter grammar.

    Computed live in SQL — no precomputed aggregation properties, no sync-time
    materialization. At this scale a GROUP BY costs less than the machinery
    needed to keep a cached value honest, and a stale metric is worse than a
    slow one. `avg_duration_days` is what makes a question like "average PR
    cycle time per repo" answerable without fetching every PR and computing
    it in Python — the two-timestamp interval a plain `avg` can't express.
    """
    from context_fabric.retrieval.query_compiler import _column_for, compile_metrics

    try:
        relations = await resolve_relations(session, request.query)
        predicate = compile_group(request.query, relations)
        group_cols = [_column_for(p) for p in request.group_by]
        metric_cols = compile_metrics(request.metrics)
    except QueryError as exc:
        raise HTTPException(400, str(exc)) from exc

    if not group_cols:
        raise HTTPException(400, "group_by must name at least one property")

    metric_exprs = [expr.label(key) for key, expr in metric_cols]
    stmt = (
        select(*group_cols, *metric_exprs)
        .where(NodeORM.deleted_at.is_(None), predicate)
        .group_by(*group_cols)
        .order_by(metric_exprs[0].desc())
    )
    rows = (await session.execute(stmt)).all()
    metric_keys = [key for key, _ in metric_cols]
    return [
        {
            **dict(zip(request.group_by, row[: len(request.group_by)], strict=True)),
            **dict(zip(metric_keys, row[len(request.group_by) :], strict=True)),
        }
        for row in rows
    ]


@router.get("/schema")
async def describe_schema(
    kind: str | None = None, session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    """What is actually queryable — derived from live data, not declared.

    `node.kind` is a free string with no enum behind it, so the set of
    "blueprints" only exists as whatever has been synced. An agent cannot write
    a query without this, and hardcoding a vocabulary would drift the moment a
    connector adds a type.
    """
    kind_stmt = (
        select(NodeORM.source_system, NodeORM.kind, func.count().label("node_count"))
        .where(NodeORM.deleted_at.is_(None))
        .group_by(NodeORM.source_system, NodeORM.kind)
        .order_by(func.count().desc())
    )
    if kind:
        kind_stmt = kind_stmt.where(NodeORM.kind == kind)
    kinds = [
        {"kind": r.kind, "source_system": r.source_system, "count": r.node_count}
        for r in (await session.execute(kind_stmt)).all()
    ]

    attr_stmt = (
        select(NodeORM.kind, func.jsonb_object_keys(NodeORM.attributes).label("attr"))
        .where(NodeORM.deleted_at.is_(None))
        .distinct()
    )
    if kind:
        attr_stmt = attr_stmt.where(NodeORM.kind == kind)
    properties: dict[str, list[str]] = {}
    for row in (await session.execute(attr_stmt)).all():
        properties.setdefault(row.kind, []).append(row.attr)

    edge_stmt = (
        select(EdgeORM.type, func.count().label("edge_count"))
        .where(EdgeORM.deleted_at.is_(None))
        .group_by(EdgeORM.type)
        .order_by(func.count().desc())
    )
    relations = [
        {"relation": r.type, "count": r.edge_count}
        for r in (await session.execute(edge_stmt)).all()
    ]

    return {
        "kinds": kinds,
        "properties": {k: sorted(v) for k, v in properties.items()},
        "relations": relations,
        "meta_properties": [
            "$identifier",
            "$title",
            "$blueprint",
            "$source",
            "$layer",
            "$path",
            "$description",
            "$createdAt",
            "$updatedAt",
            "$syncedAt",
        ],
    }
