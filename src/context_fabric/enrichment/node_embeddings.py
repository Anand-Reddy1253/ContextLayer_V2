"""On-demand embedding generation for non-Confluence technical nodes
(Azure DevOps, GitHub, Jira) — extends the semantic-search coverage built
for Confluence pages (enrichment/confluence_abstracts.py) to work items,
pull requests, issues, and similar "real content" kinds across every other
connector, using the same mechanism: walk the connector read-only to
populate its per-call content cache (same reason as confluence_abstracts.py
— get_content() only serves native_ids the connector has already seen this
session), fetch + strip each candidate node's body, embed it, and store the
vector as attributes.embedding — gated on attributes.embedding_source_hash
matching node.content_hash, same idempotency spirit as
confluence_abstracts.py and synchronization/idempotency.py.

No LLM abstract generation here, deliberately — unlike Confluence pages,
these kinds already carry a real vendor-supplied name/description most of
the time, so the "no description at all" gap ADR-010's abstracts exist for
doesn't apply the same way. Embeddings only, for the opt-in `semantic=true`
path on `/search-cards` (retrieval/semantic.py) — the search index doesn't
care which module wrote `attributes.embedding`, so this needs no changes
anywhere else once nodes carry the attribute.

Triggered only via POST /api/connectors/{id}/enrich
(api/routes/connectors.py) — never by sync itself (ADR-003).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

import structlog

from context_fabric.connectors.base import SourceConnector
from context_fabric.domain.errors import ConnectorError
from context_fabric.enrichment.html_text import strip_html
from context_fabric.enrichment.ollama_client import EnrichmentError, OllamaClient
from context_fabric.persistence.repositories.node import NodeRepository

logger = structlog.get_logger()

# An include-list, not an exclude-list — deliberately: a new connector or
# a new kind on an existing one should NOT get embedded by default just
# because nobody thought to exclude it (a build/pipeline/environment kind
# is real data but not the kind of "topic to search for" this exists for).
# Extend this set explicitly when a new kind is worth embedding.
EMBEDDABLE_KINDS: frozenset[str] = frozenset(
    {
        "BUG",
        "TASK",
        "STORY",
        "EPIC",
        "FEATURE",
        "WORK_ITEM",
        "PULL_REQUEST",
        "ISSUE",
        "TEST_CASE",
        "TEST_SUITE",
    }
)


@dataclass
class NodeEmbeddingStats:
    nodes_scanned: int = 0
    embeddings_generated: int = 0
    skipped_unchanged: int = 0
    skipped_not_synced: int = 0
    errors: int = 0


async def _collect_candidate_native_ids(connector: SourceConnector) -> list[str]:
    """Read-only BFS over the connector's hierarchy — same shape as
    synchronization/orchestrator.py's `_sync_hierarchy` and
    confluence_abstracts.py's own walk, minus every node/edge write."""
    native_ids: list[str] = []
    containers = await connector.discover_containers()
    queue: deque[str] = deque(c.native_id for c in containers)
    expanded: set[str] = set(queue)

    while queue:
        parent_native_id = queue.popleft()
        cursor: str | None = None
        while True:
            page = await connector.list_children(parent_native_id, cursor)
            for child in page.items:
                if child.kind in EMBEDDABLE_KINDS:
                    native_ids.append(child.native_id)
                if child.native_id not in expanded:
                    expanded.add(child.native_id)
                    queue.append(child.native_id)
            cursor = page.next_cursor
            if cursor is None:
                break

    return native_ids


async def enrich_node_embeddings(
    connector: SourceConnector,
    node_repo: NodeRepository,
    ollama: OllamaClient,
    *,
    source_instance_id: str,
    embed_model: str,
    force: bool = False,
) -> NodeEmbeddingStats:
    """`force=True` regenerates every candidate node's embedding
    regardless of `embedding_source_hash`, for a manual re-run after e.g.
    changing the embedding model."""
    stats = NodeEmbeddingStats()
    candidate_native_ids = await _collect_candidate_native_ids(connector)

    for native_id in candidate_native_ids:
        stats.nodes_scanned += 1

        node = await node_repo.get_by_technical_identity(
            connector.source_system, source_instance_id, native_id
        )
        if node is None or node.deleted_at is not None:
            # Discovered by the walk but not yet in the catalog — sync
            # hasn't run for it yet. Enrichment never creates a node.
            stats.skipped_not_synced += 1
            continue

        if not force and node.attributes.get("embedding_source_hash") == node.content_hash:
            stats.skipped_unchanged += 1
            continue

        # Prefer the already-synced vendor description when there is one
        # (e.g. Azure DevOps PRs: mapper.py bounds it to 512 chars and
        # stores it directly on the node) — no connector call needed.
        # Only fall back to get_content() for kinds that don't carry a
        # description at sync time (ADR-003's usual "fetch full content
        # on demand" path — work items, issues).
        text = strip_html(node.description or "", max_chars=3000).strip()
        if not text:
            try:
                content = await connector.get_content(native_id)
                text = strip_html(content.text or "", max_chars=3000).strip()
            except ConnectorError:
                # No get_content support for this kind (found live: ADO's
                # get_content() has no PR branch at all) *or* the vendor
                # genuinely has nothing stored (some real PRs here have an
                # empty description AND no fetchable content) — either
                # way, not a hard failure, just nothing beyond the name.
                text = ""
        if not text:
            # No body anywhere (a title-only ticket, common for quick
            # bugs/tasks) — embed the name alone rather than skip
            # outright; a short but real signal beats none.
            text = node.name

        try:
            vector = await ollama.embed(f"search_document: {text}", model=embed_model)
        except EnrichmentError as exc:
            logger.warning(
                "enrichment.node_embedding_failed",
                native_id=native_id,
                source_system=connector.source_system,
                source_instance_id=source_instance_id,
                error=str(exc),
            )
            stats.errors += 1
            continue

        node.attributes = {
            **node.attributes,
            "embedding": vector,
            "embedding_model": embed_model,
            "embedding_source_hash": node.content_hash,
        }
        await node_repo.update(node)
        stats.embeddings_generated += 1

    return stats
