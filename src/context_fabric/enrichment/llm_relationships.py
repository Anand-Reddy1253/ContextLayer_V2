"""On-demand LLM-inferred relationship extraction (ADR-011) — the deferred
half of Confluence relationship extraction that nothing deterministic can
find, because it's stated in prose ("this supersedes the June proposal"),
not a structured macro or vendor field.

One model call per already-synced, already-classified document (never a
pairwise comparison between two documents — see ollama_client.py's
`extract_document_relationships`): the model reads one page and a closed
list of known service/product names, and returns which services the page
concerns plus which other documents it references, in its own words. This
module then resolves those extracted identities into real edges via cheap,
deterministic matching only — an exact match against the same closed
service vocabulary the model was given, and fuzzy title matching (same
SequenceMatcher-based scoring/threshold discipline as
api/routes/catalog.py's `_score_match` fuzzy tier) against other already-
classified documents' titles. The model never sees a second document.

Every resulting edge is `origin=EdgeOrigin.LLM_INFERRED`,
`state=EdgeState.PROPOSED` unconditionally — never auto-confirmed at any
confidence, the core safety property ADR-011 documents. Content-hash-gated,
on-demand, triggered only via POST /api/connectors/{id}/enrich
(api/routes/connectors.py) — never by sync itself (ADR-003).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from difflib import SequenceMatcher
from uuid import UUID

import structlog

from context_fabric.connectors.base import SourceConnector
from context_fabric.domain.config import load_relationships
from context_fabric.domain.edge import Edge
from context_fabric.domain.enums import EdgeOrigin, EdgeState, EdgeType, Layer
from context_fabric.domain.node import Node
from context_fabric.enrichment.confluence_abstracts import collect_page_native_ids
from context_fabric.enrichment.html_text import strip_html
from context_fabric.enrichment.ollama_client import EnrichmentError, OllamaClient
from context_fabric.persistence.repositories.edge import EdgeRepository
from context_fabric.persistence.repositories.node import NodeRepository
from context_fabric.synchronization.idempotency import upsert_edge

logger = structlog.get_logger()

# Same word-level ratio/threshold as api/routes/catalog.py's _score_match
# fuzzy tier — reused, not reinvented, per the approved plan. Applied here
# per significant word of a document_hint against a candidate title's
# words, since a hint is a paraphrase of a title, not the title itself.
_FUZZY_WORD_THRESHOLD = 0.75

# Fraction of a hint's significant words that must (fuzzy-)match some word
# in a candidate title for that title to be accepted as the reference —
# calibrated conservatively: an unresolved hint is dropped and logged
# (cheap, safe), a wrongly-resolved one becomes a wrong proposed edge
# (worse, even though a human still reviews it before it's live).
_TITLE_MATCH_THRESHOLD = 0.5

# Found live: a two-word hint ("Decides on the solution.") matched "ADR-0018
# ... Schema Evolution ..." purely because SequenceMatcher("solution",
# "evolution").ratio() = 0.82 — a coincidental shared suffix, not a real
# reference. With few enough words, one lucky fuzzy hit alone can clear
# _TITLE_MATCH_THRESHOLD (1/2 = 0.5). _MIN_HINT_WORDS rules that out
# directly — a hint that short is too generic to safely bind to a specific
# document, dropped instead of resolved. _MIN_MATCHED_WORDS is a second,
# largely-redundant floor at today's constants (0.5 * 3 already implies at
# least 2 hits) — kept as insurance against a future change to
# _TITLE_MATCH_THRESHOLD or _MIN_HINT_WORDS quietly reopening the same gap.
_MIN_HINT_WORDS = 3
_MIN_MATCHED_WORDS = 2

_STOPWORDS = frozenset(
    {
        "the", "a", "an", "of", "to", "for", "in", "on", "and", "or",
        "this", "that", "from", "with", "was", "is", "are", "about",
        "document", "page", "doc", "proposal",
    }
)

_WORD_RE = re.compile(r"[a-z0-9]+")

# Fixed, not model-reported — the model's own extraction schema carries no
# numeric confidence (ollama_client.py's LLMRelationshipExtractionResult),
# and state=PROPOSED is unconditional regardless of this value anyway; it
# exists only for the review queue's own sort/filter, well under
# link_extraction.py's 0.95 auto-confirm threshold (which never applies to
# LLM_INFERRED edges in the first place).
_LLM_INFERRED_CONFIDENCE = 0.6

_RELATIONSHIP_TO_EDGE_TYPE: dict[str, EdgeType] = {
    "supersedes": EdgeType.SUPERSEDES,
    "superseded_by": EdgeType.SUPERSEDED_BY,
    "caused_by": EdgeType.CAUSED_BY,
    "decides_on": EdgeType.DECIDES_ON,
}


@dataclass
class LLMRelationshipStats:
    documents_scanned: int = 0
    documents_classified: int = 0
    skipped_unchanged: int = 0
    skipped_not_synced: int = 0
    services_proposed: int = 0
    relationships_proposed: int = 0
    unmatched_references: int = 0
    errors: int = 0


def _significant_words(text: str) -> list[str]:
    return [w for w in _WORD_RE.findall(text.lower()) if w not in _STOPWORDS and len(w) > 2]


def _hint_title_hits(hint_words: list[str], title_words: list[str]) -> int:
    """Count of `hint_words` that (exactly or fuzzily) appear among
    `title_words` — the same SequenceMatcher/threshold primitive
    catalog.py's `_score_match` uses per-word, aggregated across a whole
    hint phrase rather than a single query word."""
    if not hint_words or not title_words:
        return 0
    hits = 0
    for hw in hint_words:
        if hw in title_words or any(
            SequenceMatcher(None, hw, tw).ratio() >= _FUZZY_WORD_THRESHOLD for tw in title_words
        ):
            hits += 1
    return hits


def _resolve_document_hint(hint: str, candidates: dict[UUID, str]) -> UUID | None:
    """Best fuzzy title match for `hint` among `candidates` (doc id ->
    title), or None if nothing clears both `_TITLE_MATCH_THRESHOLD` and
    `_MIN_MATCHED_WORDS` — an unresolved hint is dropped, never retried
    with a second model call. A hint shorter than `_MIN_HINT_WORDS` is
    never even attempted: too few words for a coincidental match (one
    word alone) to be distinguishable from a real one."""
    hint_words = _significant_words(hint)
    if len(hint_words) < _MIN_HINT_WORDS:
        return None

    best_id: UUID | None = None
    best_hits = 0
    for doc_id, title in candidates.items():
        hits = _hint_title_hits(hint_words, _significant_words(title))
        if hits > best_hits:
            best_hits = hits
            best_id = doc_id

    if best_hits < _MIN_MATCHED_WORDS:
        return None
    return best_id if (best_hits / len(hint_words)) >= _TITLE_MATCH_THRESHOLD else None


async def extract_llm_relationships(
    connector: SourceConnector,
    node_repo: NodeRepository,
    edge_repo: EdgeRepository,
    ollama: OllamaClient,
    *,
    source_instance_id: str,
    model_name: str,
    force: bool = False,
) -> LLMRelationshipStats:
    """`force=True` re-runs extraction for every classified document
    regardless of its own content-hash gate, for a manual re-run after
    e.g. changing the prompt or model."""
    stats = LLMRelationshipStats()
    now = datetime.now(UTC).isoformat()
    now_dt = datetime.now(UTC)
    rules = load_relationships()

    page_native_ids = await collect_page_native_ids(connector)

    documents: list[Node] = []
    for native_id in page_native_ids:
        stats.documents_scanned += 1
        node = await node_repo.get_by_technical_identity(
            connector.source_system, source_instance_id, native_id
        )
        if node is None or node.deleted_at is not None:
            stats.skipped_not_synced += 1
            continue
        if not node.attributes.get("page_type"):
            continue
        documents.append(node)
        stats.documents_classified += 1

    # The fuzzy-match pool for `references` — every other already-
    # classified document's title, keyed by node id.
    title_index: dict[UUID, str] = {doc.id: doc.name for doc in documents}

    business_nodes = await node_repo.list_by_layer(Layer.BUSINESS)
    service_nodes = {n.name: n for n in business_nodes if n.kind in ("SERVICE", "PRODUCT")}
    known_services = list(service_nodes)

    for doc in documents:
        prior_hash = doc.attributes.get("llm_relationships_source_hash")
        if not force and prior_hash == doc.content_hash:
            stats.skipped_unchanged += 1
            continue

        content = await connector.get_content(doc.native_id)  # type: ignore[arg-type]
        text = strip_html(content.text or "", max_chars=3000)

        try:
            result = await ollama.extract_document_relationships(
                text, known_services=known_services
            )
        except EnrichmentError as exc:
            logger.warning(
                "enrichment.llm_relationships_failed",
                native_id=doc.native_id,
                source_instance_id=source_instance_id,
                error=str(exc),
            )
            stats.errors += 1
            continue

        for service_name in result.services:
            service_node = service_nodes.get(service_name)
            if service_node is None:
                continue
            if not rules.allows(EdgeType.RELATED_TO, doc.kind, service_node.kind):
                continue
            edge_candidate = Edge(
                src_id=doc.id,
                dst_id=service_node.id,
                type=EdgeType.RELATED_TO,
                origin=EdgeOrigin.LLM_INFERRED,
                state=EdgeState.PROPOSED,
                confidence=_LLM_INFERRED_CONFIDENCE,
                attributes={
                    "extracted_by": "llm",
                    "model": model_name,
                    "rationale": f"Document appears to concern the {service_name} service.",
                },
                first_seen_at=now_dt,
                last_seen_at=now_dt,
            )
            if await upsert_edge(edge_repo, edge_candidate):
                stats.services_proposed += 1

        candidates = {k: v for k, v in title_index.items() if k != doc.id}
        for reference in result.references:
            target_id = _resolve_document_hint(reference.document_hint, candidates)
            if target_id is None:
                logger.info(
                    "enrichment.llm_relationship_unresolved",
                    native_id=doc.native_id,
                    source_instance_id=source_instance_id,
                    document_hint=reference.document_hint,
                )
                stats.unmatched_references += 1
                continue

            edge_type = _RELATIONSHIP_TO_EDGE_TYPE[reference.relationship]
            target_kind = next(d.kind for d in documents if d.id == target_id)
            if not rules.allows(edge_type, doc.kind, target_kind):
                continue

            edge_candidate = Edge(
                src_id=doc.id,
                dst_id=target_id,
                type=edge_type,
                origin=EdgeOrigin.LLM_INFERRED,
                state=EdgeState.PROPOSED,
                confidence=_LLM_INFERRED_CONFIDENCE,
                attributes={
                    "extracted_by": "llm",
                    "model": model_name,
                    "rationale": reference.document_hint,
                },
                first_seen_at=now_dt,
                last_seen_at=now_dt,
            )
            if await upsert_edge(edge_repo, edge_candidate):
                stats.relationships_proposed += 1

        new_attrs = dict(doc.attributes)
        new_attrs["llm_relationships_source_hash"] = doc.content_hash
        new_attrs["llm_relationships_generated_at"] = now
        doc.attributes = new_attrs
        await node_repo.update(doc)

    return stats
