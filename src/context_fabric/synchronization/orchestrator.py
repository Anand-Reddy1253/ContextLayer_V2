"""Sync orchestrator — connectors -> domain -> persistence
(docs/architecture.md §4 "Sync data flow").

  discover_containers -> BFS list_children (respecting cursors) -> map
    -> content_hash diff -> upsert node -> structural CONTAINS edges
    -> get_links extraction (Phase 7) -> two tombstone sweeps

Structural CONTAINS edges and extracted MENTIONS/RELATED_TO edges both go
through idempotency.py's upsert_edge, so re-running sync never duplicates
either kind.

Two tombstone sweeps run after every successful hierarchy sync, in order:
`_sweep_tombstones` (precise, connector-specific — today only Azure DevOps
work items via the Recycle Bin API) and `_sweep_stale` (general-purpose,
every connector: diffs the full set of native_ids just walked against
what's still marked active in the DB for that connector instance — see its
own docstring for the safety guards around degraded entity types and
narrowed container selection).
"""

from __future__ import annotations

import hashlib
import json
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from context_fabric.connectors.base import SourceConnector, correlate
from context_fabric.domain.edge import Edge
from context_fabric.domain.enums import EdgeOrigin, EdgeType, Layer
from context_fabric.domain.errors import ConnectorError
from context_fabric.domain.ltree import sanitize_label
from context_fabric.domain.node import Node
from context_fabric.domain.sync import SyncRun
from context_fabric.persistence.repositories.edge import EdgeRepository
from context_fabric.persistence.repositories.node import NodeRepository
from context_fabric.persistence.repositories.sync_run import SyncRunRepository
from context_fabric.persistence.repositories.sync_state import SyncStateRepository
from context_fabric.synchronization import state as sync_state_module
from context_fabric.synchronization.idempotency import upsert_edge, upsert_node
from context_fabric.synchronization.link_extraction import extract_links_for_node


def _hash_attributes(attributes: dict) -> str:
    """Containers (SourceContainer) carry no content_hash of their own
    (docs/DOMAIN_MODEL.md "Connector-facing types") — compute one from
    their attributes so idempotency comparison stays uniform for every
    node kind, container or object."""
    payload = json.dumps(attributes, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass
class SyncStats:
    nodes_upserted: int = 0
    nodes_tombstoned: int = 0
    edges_created: int = 0
    # Every native_id actually walked this pass (discover_containers +
    # list_children, both container and child) — _sweep_stale's
    # generalized tombstone diff below reuses this instead of asking each
    # connector to implement its own deletion feed.
    expanded: set[str] = field(default_factory=set)
    # True only once _sync_hierarchy has walked every container to
    # completion — never set on a partial or incremental pass. _sweep_stale
    # refuses to run without it: its whole correctness depends on
    # `expanded` being the *complete* current state, not just what changed.
    # An incremental ("since last watermark") pass only ever populates a
    # subset of `expanded` — if that ran through the same sweep, every node
    # not touched by today's delta would read as "deleted," and every edge
    # touching it would cascade-delete with it. Today nothing calls
    # _sweep_stale from anywhere but a full walk, so this can't fire yet —
    # but that's a convention, and this codebase has already had two
    # conventions break silently this session (the confidence policy, the
    # title/body concatenation). This makes the invariant enforced rather
    # than remembered.
    walk_complete: bool = False


SyncMode = Literal["full", "incremental"]


async def sync_source(
    session: AsyncSession,
    connector: SourceConnector,
    *,
    source_instance_id: str,
    correlation_id: str | None = None,
    mode: SyncMode = "full",
) -> SyncRun:
    """Runs one sync pass for `connector`, scoped to `source_instance_id`
    (e.g. "ado-acme"). Records a SyncRun regardless of outcome; re-raises
    the connector error after recording failure.

    `mode="incremental"` fetches only what changed since the connector's
    stored cursor (SyncState.cursor) via the connector's own
    `list_changed_since`, when it has one — duck-typed, not part of
    `SourceConnector`, since not every connector implements it yet (today:
    only Azure DevOps work items — see its own docstring). A connector
    without it falls back to a full pass, logged, rather than silently
    doing nothing. Either way, an incremental pass never runs either
    tombstone sweep: `SyncStats.walk_complete` stays False by construction,
    which `_sweep_stale` already refuses to run without — see that field's
    docstring for why a partial walk must never be read as "everything
    else was deleted."
    """
    node_repo = NodeRepository(session)
    edge_repo = EdgeRepository(session)
    sync_run_repo = SyncRunRepository(session)
    sync_state_repo = SyncStateRepository(session)

    with correlate(correlation_id) as cid:
        run = await sync_state_module.start_run(
            sync_run_repo,
            sync_state_repo,
            source_system=connector.source_system,
            scope_id=source_instance_id,
            correlation_id=cid,
        )
        try:
            actual_mode = mode
            if mode == "incremental" and not hasattr(connector, "list_changed_since"):
                structlog.get_logger().info(
                    "sync.incremental_unsupported_falling_back_to_full",
                    source_system=connector.source_system,
                    source_instance_id=source_instance_id,
                )
                actual_mode = "full"

            if actual_mode == "incremental":
                prior_state = await sync_state_repo.get(connector.source_system, source_instance_id)
                stats, new_cursor = await _sync_incremental(
                    node_repo,
                    edge_repo,
                    connector,
                    source_instance_id,
                    cursor=prior_state.cursor if prior_state else None,
                )
            else:
                stats = await _sync_hierarchy(node_repo, edge_repo, connector, source_instance_id)
                await _sweep_tombstones(node_repo, edge_repo, connector, source_instance_id, stats)
                await _sweep_stale(node_repo, edge_repo, connector, source_instance_id, stats)
                new_cursor = None
        except ConnectorError as exc:
            await sync_state_module.finish_run_failure(sync_run_repo, sync_state_repo, run, exc)
            raise
        return await sync_state_module.finish_run_success(
            sync_run_repo,
            sync_state_repo,
            run,
            nodes_upserted=stats.nodes_upserted,
            nodes_tombstoned=stats.nodes_tombstoned,
            edges_created=stats.edges_created,
            walk_complete=stats.walk_complete,
            cursor=new_cursor,
        )


async def _sync_hierarchy(
    node_repo: NodeRepository,
    edge_repo: EdgeRepository,
    connector: SourceConnector,
    source_instance_id: str,
) -> SyncStats:
    stats = SyncStats()
    now = datetime.now(UTC)

    containers = await connector.discover_containers()
    queue: deque[tuple[str, Node]] = deque()
    # Tracks every native_id ever enqueued for expansion (i.e. we've
    # called or will call list_children on it), so a connector that
    # returns the same child under two parents — or, worse, a bug that
    # makes list_children(X) return X itself — can never grow the queue
    # without bound. Node upsert/edges/link-extraction still happen every
    # time a node is *encountered*, just not repeated expansion.
    expanded: set[str] = set()

    for container in containers:
        candidate = Node(
            layer=Layer.TECHNICAL,
            kind=container.kind,
            name=container.name,
            description=container.description,
            path=sanitize_label(container.native_id),
            source_system=connector.source_system,
            source_instance_id=source_instance_id,
            native_id=container.native_id,
            attributes=container.attributes,
            content_hash=_hash_attributes(container.attributes),
            first_seen_at=now,
            last_seen_at=now,
            created_at=now,
            updated_at=now,
        )
        result = await upsert_node(node_repo, candidate)
        if result.changed:
            stats.nodes_upserted += 1

        link_stats = await extract_links_for_node(
            node_repo,
            edge_repo,
            connector,
            from_node_id=result.node.id,
            from_native_id=container.native_id,
            from_kind=result.node.kind,
            now=now,
        )
        stats.edges_created += link_stats.edges_created

        queue.append((container.native_id, result.node))
        expanded.add(container.native_id)

    while queue:
        parent_native_id, parent_node = queue.popleft()
        cursor: str | None = None
        while True:
            page = await connector.list_children(parent_native_id, cursor)
            for child in page.items:
                child_path = f"{parent_node.path}.{sanitize_label(child.native_id)}"
                candidate = Node(
                    layer=Layer.TECHNICAL,
                    kind=child.kind,
                    name=child.name,
                    description=child.description,
                    parent_id=parent_node.id,
                    path=child_path,
                    source_system=connector.source_system,
                    source_instance_id=source_instance_id,
                    native_id=child.native_id,
                    attributes=child.attributes,
                    source_version=child.source_version,
                    content_hash=child.content_hash,
                    first_seen_at=now,
                    last_seen_at=now,
                    created_at=now,
                    updated_at=now,
                )
                result = await upsert_node(node_repo, candidate)
                if result.changed:
                    stats.nodes_upserted += 1

                edge_candidate = Edge(
                    src_id=parent_node.id,
                    dst_id=result.node.id,
                    type=EdgeType.CONTAINS,
                    origin=EdgeOrigin.SYNC_STRUCTURAL,
                    first_seen_at=now,
                    last_seen_at=now,
                )
                if await upsert_edge(edge_repo, edge_candidate):
                    stats.edges_created += 1

                link_stats = await extract_links_for_node(
                    node_repo,
                    edge_repo,
                    connector,
                    from_node_id=result.node.id,
                    from_native_id=child.native_id,
                    from_kind=result.node.kind,
                    now=now,
                )
                stats.edges_created += link_stats.edges_created

                if child.native_id not in expanded:
                    expanded.add(child.native_id)
                    queue.append((child.native_id, result.node))

            cursor = page.next_cursor
            if cursor is None:
                break

    stats.expanded = expanded
    # Reached only if the queue drained without raising — every container
    # was walked to completion, so `expanded` is genuinely the whole
    # current state, not a partial one. This is the one place it's safe to
    # set (see the field's own docstring).
    stats.walk_complete = True
    return stats


async def _sync_incremental(
    node_repo: NodeRepository,
    edge_repo: EdgeRepository,
    connector: SourceConnector,
    source_instance_id: str,
    *,
    cursor: str | None,
) -> tuple[SyncStats, str | None]:
    """Upserts only what `connector.list_changed_since(cursor)` reports —
    see `sync_source`'s own docstring for why this never runs either
    tombstone sweep (`SyncStats.walk_complete` stays at its default False).

    A changed item's parent must already exist for its `path` to be
    computed — true for anything that was already synced by at least one
    prior full pass, which is the only situation this is ever called in
    (`sync_source` falls back to a full pass when there's no cursor-bearing
    connector support at all). An item whose parent genuinely isn't found
    is skipped with a warning rather than guessed at; the next full
    reconciliation pass picks it up correctly, with its real ancestry."""
    stats = SyncStats()
    now = datetime.now(UTC)
    logger = structlog.get_logger()

    page = await connector.list_changed_since(cursor)  # type: ignore[attr-defined]
    for child in page.items:
        parent_node = None
        if child.parent_native_id is not None:
            parent_node = await node_repo.get_by_technical_identity(
                connector.source_system, source_instance_id, child.parent_native_id
            )
            if parent_node is None:
                logger.warning(
                    "sync.incremental_orphan_skipped",
                    source_system=connector.source_system,
                    source_instance_id=source_instance_id,
                    native_id=child.native_id,
                    parent_native_id=child.parent_native_id,
                )
                continue

        path = (
            f"{parent_node.path}.{sanitize_label(child.native_id)}"
            if parent_node is not None
            else sanitize_label(child.native_id)
        )
        candidate = Node(
            layer=Layer.TECHNICAL,
            kind=child.kind,
            name=child.name,
            description=child.description,
            parent_id=parent_node.id if parent_node is not None else None,
            path=path,
            source_system=connector.source_system,
            source_instance_id=source_instance_id,
            native_id=child.native_id,
            attributes=child.attributes,
            source_version=child.source_version,
            content_hash=child.content_hash,
            first_seen_at=now,
            last_seen_at=now,
            created_at=now,
            updated_at=now,
        )
        result = await upsert_node(node_repo, candidate)
        if result.changed:
            stats.nodes_upserted += 1

        if parent_node is not None:
            edge_candidate = Edge(
                src_id=parent_node.id,
                dst_id=result.node.id,
                type=EdgeType.CONTAINS,
                origin=EdgeOrigin.SYNC_STRUCTURAL,
                first_seen_at=now,
                last_seen_at=now,
            )
            if await upsert_edge(edge_repo, edge_candidate):
                stats.edges_created += 1

        link_stats = await extract_links_for_node(
            node_repo,
            edge_repo,
            connector,
            from_node_id=result.node.id,
            from_native_id=child.native_id,
            from_kind=result.node.kind,
            now=now,
        )
        stats.edges_created += link_stats.edges_created
        stats.expanded.add(child.native_id)

    # walk_complete deliberately left False — see SyncStats' own docstring.
    return stats, page.next_cursor


async def _sweep_tombstones(
    node_repo: NodeRepository,
    edge_repo: EdgeRepository,
    connector: SourceConnector,
    source_instance_id: str,
    stats: SyncStats,
) -> None:
    """Precise deletion signal, where a connector has one (today: Azure
    DevOps work items, via the Recycle Bin API — docs/CONNECTORS.md
    "Deletion detection"). Most entity types across every connector have
    no such feed at all; `_sweep_stale` below is the general-purpose
    fallback that covers those."""
    now = datetime.now(UTC)
    cursor: str | None = None
    while True:
        page = await connector.get_changes(cursor)
        for item in page.items:
            if not item.deleted:
                continue
            existing = await node_repo.get_by_technical_identity(
                connector.source_system, source_instance_id, item.native_id
            )
            if existing is not None and existing.deleted_at is None:
                await node_repo.soft_delete(existing.id, now)
                await edge_repo.soft_delete_touching(existing.id, now)
                stats.nodes_tombstoned += 1
        if not page.has_more or page.next_cursor is None:
            break
        cursor = page.next_cursor


async def _sweep_stale(
    node_repo: NodeRepository,
    edge_repo: EdgeRepository,
    connector: SourceConnector,
    source_instance_id: str,
    stats: SyncStats,
) -> None:
    """General-purpose deletion detection for every connector, not just
    the ones with their own delta/recycle-bin feed: a full sync pass
    (`_sync_hierarchy`) already walks every object the connector reports
    right now (`stats.expanded`) — anything still marked active in our DB
    for this connector instance but absent from that walk no longer
    exists upstream (or is no longer reachable, same practical effect).

    If any optional entity type degraded this pass
    (connector.degraded_entity_types, set via
    LiveConnectorBase._mark_degraded — a permission hiccup or transient
    error, which must never be read as "everything of that type was
    deleted"), the node *kinds* that entity type produces
    (connector.ENTITY_TYPE_KINDS, declared per connector) are excluded
    from this sweep — everything else still gets swept normally. A real
    case this guards against: `environments` and `test_runs` fail on
    every sync in this environment (401/400, a permission gap and a
    known ADO API quirk respectively) — under a whole-connector skip
    that meant builds, PRs, and work items could never be pruned either,
    just because two unrelated optional types keep erroring. Falls back
    to skipping the connector's *entire* sweep, logged, only if it
    declares no ENTITY_TYPE_KINDS mapping at all — better to skip than
    guess which kinds a degraded type might own.

    Also skipped entirely whenever this connection narrows sync to a
    subset of containers (`_selected_containers` — every live
    connector's project/org/space picker, docs/UI.md "Connectors"): a
    deselected container's nodes are legitimately absent from
    `stats.expanded` too, and that's "not synced anymore," not "deleted
    upstream" — conflating the two would tombstone a whole project's
    subtree the moment someone narrows their selection. Distinguishing
    "deselected" from "deleted" precisely would need per-node container
    ancestry this sweep doesn't have.

    Requires `stats.walk_complete` — see that field's own docstring. This
    is the load-bearing guard against an incremental ("changed since X")
    sync pass ever reaching this sweep: `expanded` from a partial walk
    would make every untouched node look deleted, cascading real edges
    away along with them. Refusing outright, rather than trusting every
    future caller to remember not to invoke this on a delta pass."""
    if not stats.walk_complete:
        structlog.get_logger().warning(
            "sync.stale_sweep_skipped",
            source_system=connector.source_system,
            source_instance_id=source_instance_id,
            reason="walk_incomplete",
        )
        return
    if getattr(connector, "_selected_containers", None) is not None:
        structlog.get_logger().warning(
            "sync.stale_sweep_skipped",
            source_system=connector.source_system,
            source_instance_id=source_instance_id,
            reason="selected_containers_narrowed",
        )
        return

    degraded = getattr(connector, "degraded_entity_types", None)
    skip_kinds: set[str] = set()
    if degraded:
        entity_type_kinds = getattr(connector, "ENTITY_TYPE_KINDS", None)
        if entity_type_kinds is None:
            structlog.get_logger().warning(
                "sync.stale_sweep_skipped",
                source_system=connector.source_system,
                source_instance_id=source_instance_id,
                reason="degraded_entity_types_unmapped",
                degraded_entity_types=sorted(degraded),
            )
            return
        for entity_type in degraded:
            skip_kinds |= entity_type_kinds.get(entity_type, set())
        structlog.get_logger().warning(
            "sync.stale_sweep_kinds_excluded",
            source_system=connector.source_system,
            source_instance_id=source_instance_id,
            degraded_entity_types=sorted(degraded),
            excluded_kinds=sorted(skip_kinds),
        )

    now = datetime.now(UTC)
    active = await node_repo.list_active_native_ids(connector.source_system, source_instance_id)
    for node_id, native_id, kind in active:
        if kind in skip_kinds:
            continue
        if native_id in stats.expanded:
            continue
        await node_repo.soft_delete(node_id, now)
        await edge_repo.soft_delete_touching(node_id, now)
        stats.nodes_tombstoned += 1
