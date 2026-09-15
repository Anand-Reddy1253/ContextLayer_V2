"""On-demand Confluence page enrichment — walks a connector's read-only
hierarchy (mirroring synchronization/orchestrator.py's BFS, but writing
nothing to node_repo during the walk itself) purely to populate the
connector's per-call content cache, since get_content()
(connectors/confluence/live.py) only ever reads from that cache. For each
already-synced PAGE node whose body has changed since its last generation
(content_hash-gated, same idempotency spirit as
synchronization/idempotency.py), fetches the body, strips it to plain text,
and asks the configured OllamaClient for a bounded abstract + keyword list —
written onto attributes.llm_abstract / attributes.llm_keywords, never onto
node.description (ADR-010: vendor-sourced description always takes
precedence over a generated one) — plus a dense embedding vector
(attributes.embedding) for the opt-in `semantic=true` path on
`/search-cards` (retrieval/semantic.py).

The abstract and the embedding are gated on content_hash *independently* —
not as one combined "is this page stale" check — so a page enriched before
embeddings existed gets its embedding backfilled on the next run without
needlessly regenerating an already-correct abstract, and a failure in one
never loses a successful result from the other (each is its own
try/except).

Triggered only via POST /api/connectors/{id}/enrich
(api/routes/connectors.py) — never by sync itself (ADR-003).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime

import structlog

from context_fabric.connectors.base import SourceConnector
from context_fabric.enrichment.html_text import strip_html
from context_fabric.enrichment.ollama_client import EnrichmentError, OllamaClient
from context_fabric.persistence.repositories.node import NodeRepository

logger = structlog.get_logger()


@dataclass
class EnrichmentStats:
    pages_scanned: int = 0
    abstracts_generated: int = 0
    embeddings_generated: int = 0
    skipped_unchanged: int = 0
    skipped_not_synced: int = 0
    errors: int = 0


async def _collect_page_native_ids(connector: SourceConnector) -> list[str]:
    """Read-only BFS over the connector's hierarchy — same shape as
    synchronization/orchestrator.py's `_sync_hierarchy`, minus every
    node/edge write. Needed purely so get_content() has a populated cache
    to read from (confluence/live.py's get_content only serves content for
    native_ids the connector has already seen this session)."""
    page_native_ids: list[str] = []
    containers = await connector.discover_containers()
    queue: deque[str] = deque(c.native_id for c in containers)
    expanded: set[str] = set(queue)

    while queue:
        parent_native_id = queue.popleft()
        cursor: str | None = None
        while True:
            page = await connector.list_children(parent_native_id, cursor)
            for child in page.items:
                if child.kind == "PAGE":
                    page_native_ids.append(child.native_id)
                if child.native_id not in expanded:
                    expanded.add(child.native_id)
                    queue.append(child.native_id)
            cursor = page.next_cursor
            if cursor is None:
                break

    return page_native_ids


async def enrich_confluence_pages(
    connector: SourceConnector,
    node_repo: NodeRepository,
    ollama: OllamaClient,
    *,
    source_instance_id: str,
    embed_model: str,
    force: bool = False,
) -> EnrichmentStats:
    """`force=True` regenerates every page's abstract *and* embedding
    regardless of their own source-hash gates, for a manual re-run after
    e.g. changing the prompt or model."""
    stats = EnrichmentStats()
    now = datetime.now(UTC).isoformat()

    page_native_ids = await _collect_page_native_ids(connector)

    for native_id in page_native_ids:
        stats.pages_scanned += 1

        node = await node_repo.get_by_technical_identity(
            connector.source_system, source_instance_id, native_id
        )
        if node is None or node.deleted_at is not None:
            # Discovered by the walk but not yet in the catalog — sync
            # hasn't run for it yet. Enrichment never creates a node.
            stats.skipped_not_synced += 1
            continue

        prior_abstract_hash = node.attributes.get("llm_abstract_source_hash")
        prior_embedding_hash = node.attributes.get("embedding_source_hash")
        need_abstract = force or prior_abstract_hash != node.content_hash
        need_embedding = force or prior_embedding_hash != node.content_hash
        if not need_abstract and not need_embedding:
            stats.skipped_unchanged += 1
            continue

        new_attrs = dict(node.attributes)
        changed = False
        text: str | None = None
        if need_abstract or need_embedding:
            content = await connector.get_content(native_id)
            # 3000 chars, not html_text's 8000 default — measured live
            # against this model/hardware (llama3.2:1b, CPU-only): an
            # ~7200-char input took ~200s to generate, well past the
            # client's timeout, and repeatedly failed every retry
            # identically (a real page, not a fixture — ADR-0011 in the
            # live Confluence org). Smaller input is both faster and, for
            # a 1.2B-parameter model, generally a better summary anyway.
            text = strip_html(content.text or "", max_chars=3000)

        if need_abstract:
            try:
                result = await ollama.generate_abstract(text or "")
            except EnrichmentError as exc:
                logger.warning(
                    "enrichment.confluence_page_abstract_failed",
                    native_id=native_id,
                    source_instance_id=source_instance_id,
                    error=str(exc),
                )
                stats.errors += 1
            else:
                new_attrs.update(
                    llm_abstract=result.abstract,
                    llm_keywords=result.keywords,
                    description_origin="llm",
                    llm_abstract_source_hash=node.content_hash,
                    llm_abstract_generated_at=now,
                )
                changed = True
                stats.abstracts_generated += 1

        if need_embedding:
            try:
                # nomic-embed-text is trained with asymmetric task prefixes
                # ("search_document:" for indexed content, "search_query:"
                # for the query side, see _semantic_merge in catalog.py) —
                # without them retrieval quality degrades noticeably
                # (measured live: a real ADR page ranked mid-pack for a
                # clearly-related one-word query before this was added).
                vector = await ollama.embed(f"search_document: {text or ''}", model=embed_model)
            except EnrichmentError as exc:
                logger.warning(
                    "enrichment.confluence_page_embed_failed",
                    native_id=native_id,
                    source_instance_id=source_instance_id,
                    error=str(exc),
                )
                stats.errors += 1
            else:
                new_attrs.update(
                    embedding=vector,
                    embedding_model=embed_model,
                    embedding_source_hash=node.content_hash,
                )
                changed = True
                stats.embeddings_generated += 1

        if changed:
            node.attributes = new_attrs
            await node_repo.update(node)

    return stats
