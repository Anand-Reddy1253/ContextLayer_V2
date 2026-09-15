"""Link extraction — turns SourceConnector.get_links() output into
MENTIONS/RELATED_TO edges (docs/architecture.md §5 "Actual lineage vs.
structural containment"). Runs as part of the hierarchy sync
(orchestrator.py), after each node is upserted, so link targets have a
chance to already exist in the graph — including nodes from a different
connector synced earlier, which is how cross-connector edges appear.

Extracted edges land as origin=SYNC_EXTRACTED, state=PROPOSED — a human
confirms/rejects/retypes them later in the UI (docs/UI.md "Proposed links
review"); they are never auto-promoted to ACTIVE here.

An unresolvable target_ref is not a hard failure — it's logged
(`link_extraction.unresolved`) so a later sync pass (once the target
finally exists) or a UI surface can revisit it. Not persisted to a
dedicated table in this phase: docs/phases/PHASE-07.md offered "table or
log" as alternatives, and a structured log line is enough for a fixture-
scale PoC — add a table if a real retry UI ever needs to query the
backlog directly.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from re import Match
from uuid import UUID

import structlog

from context_fabric.connectors.base import SourceConnector
from context_fabric.domain.config import RelationshipsConfig, load_relationships
from context_fabric.domain.edge import Edge
from context_fabric.domain.enums import EdgeOrigin, EdgeState, EdgeType
from context_fabric.domain.node import Node
from context_fabric.persistence.repositories.edge import EdgeRepository
from context_fabric.persistence.repositories.node import NodeRepository
from context_fabric.synchronization.idempotency import upsert_edge

logger = structlog.get_logger()


@lru_cache(maxsize=1)
def _relationship_rules() -> RelationshipsConfig:
    """Loaded once per process, not per call — sync processes many nodes
    per run and this file never changes mid-run. Module-level cache
    rather than the eager-at-startup convention domain/config.py's other
    loaders describe, since nothing in this codebase has a startup hook
    to call it from yet; this is still "loaded once," just lazily on
    first use instead of at process boot."""
    return load_relationships()

# (pattern, target source_system, native_id extractor). Add a row here for
# each new cross-reference shape a connector's get_links() can produce —
# e.g. a future Jira connector's "PROJ-(\d+)" (docs/CONNECTORS.md).
LinkPattern = tuple[re.Pattern[str], str, Callable[[Match[str]], str]]

LINK_PATTERNS: list[LinkPattern] = [
    (re.compile(r"^AB#(\d+)$"), "azure_devops", lambda m: m.group(1)),
    (re.compile(r"^PR-\d+$"), "azure_devops", lambda m: m.group(0)),
    # A Build's own `repository.id` (ADO's repo GUID) — a direct match,
    # not text-mined, produced by connectors/azure_devops/mapper.py's
    # map_build_links. Strips the prefix back to the bare GUID, which is
    # exactly what map_git_repository sets as the repo node's native_id.
    (re.compile(r"^REPO-(.+)$"), "azure_devops", lambda m: m.group(1)),
    # Confluence's own internal page-to-page link macro's `ri:content-id`
    # — produced by connectors/confluence/mapper.py's
    # _INTERNAL_PAGE_LINK_PATTERN. Strips the prefix back to Confluence's
    # bare page id, exactly what map_page sets as the page node's
    # native_id.
    (re.compile(r"^CONFPAGE-(\d+)$"), "confluence", lambda m: m.group(1)),
    # GitHub's own Issue/PR native_id shape ("{repo}#{number}") — produced
    # by connectors/github/mapper.py's own #NN / owner/repo#NN extraction
    # and connectors/confluence/mapper.py's owner/repo#NN extraction; the
    # whole match is already GitHub's native_id, nothing to strip.
    (re.compile(r"^[\w.\-]+/[\w.\-]+#\d+$"), "github", lambda m: m.group(0)),
    # Jira's own issue-key shape ("PROJ-123") — a project key is 2-10
    # uppercase letters/digits starting with a letter (Jira's real
    # constraint). Checked last so it never shadows the more specific
    # "PR-\d+" (azure_devops) pattern above — "PR" itself is a
    # syntactically valid 2-letter project key, and pattern order decides
    # which source_system a bare "PR-42" resolves against.
    (re.compile(r"^[A-Z][A-Z0-9]{1,9}-\d+$"), "jira", lambda m: m.group(0)),
]

# A link at or above this confidence skips human review entirely:
# state=ACTIVE, origin=SYNC_STRUCTURAL, same treatment as the structural
# CONTAINS hierarchy. Below it, the PROPOSED/SYNC_EXTRACTED review-queue
# path applies. 0.95 rather than 1.0 so a caller can mark something "as
# good as structural" without needing an exact float match.
_AUTO_CONFIRM_THRESHOLD = 0.95

# How much a reference resolving is worth, added to the extraction-time
# prior. SourceLink.confidence is assigned before anything knows whether
# the referenced object exists; "AB#99999" pointing at nothing is a guess,
# while "AB#412" resolving to exactly one real work item is a reference
# whose target demonstrably exists.
#
# Why this had to change at all: structured vendor fields are same-system
# by definition and score 1.0, while a reference to *another* system can
# only ever be text-mined and scored below the auto-confirm threshold. Since
# graph/traversal.py walks ACTIVE edges only, every cross-tool edge was
# invisible from creation, pending a human confirming each one. The policy
# silently encoded "same-system = trusted, cross-system = guess" — backwards
# for a context layer whose whole point is cross-tool traceability.
#
# A boost rather than a floor, deliberately. Resolution proves the target
# exists; it does not prove the relationship is meaningful. A work item id
# in a pull request *title* is the author declaring intent and clears the
# bar once resolved; the same id in a comment ("unlike AB#412, this...")
# resolves just as cleanly and still deserves a human look. Flooring every
# resolved link to the threshold would auto-confirm both and leave the
# review queue permanently empty — it would have been the same mistake in
# the opposite direction.
_RESOLUTION_BOOST = 0.10


_EDGE_TYPE_BY_LINK_KIND: dict[str, EdgeType] = {
    "mentions": EdgeType.MENTIONS,
    "relates_to": EdgeType.RELATED_TO,
    "verifies": EdgeType.VERIFIES,
    "depends_on": EdgeType.DEPENDS_ON,
    # These three existed in EdgeType from the start and were never
    # reachable — no link_kind mapped to them, so every extracted link
    # became MENTIONS or RELATED_TO regardless of how strong the evidence
    # was. connectors/cross_references.py now emits them based on where a
    # reference was found.
    "implements": EdgeType.IMPLEMENTS,
    "specifies": EdgeType.SPECIFIED_BY,
    "changes": EdgeType.CHANGES,
}


def _edge_type_for(link_kind: str) -> EdgeType:
    return _EDGE_TYPE_BY_LINK_KIND.get(link_kind, EdgeType.RELATED_TO)


@dataclass
class LinkExtractionStats:
    edges_created: int = 0
    unresolved: int = 0
    # A reference resolved to a real node but the (edge_type, src_kind,
    # dst_kind) triple has no rule in configs/relationships.yaml —
    # distinct from `unresolved` (target doesn't exist at all). This is
    # what a STORY--IMPLEMENTS-->STORY attempt becomes now, instead of a
    # silently-created wrong edge.
    rejected: int = 0


async def _resolve_target(node_repo: NodeRepository, target_ref: str) -> Node | None:
    """First pattern whose extracted native_id actually resolves to a
    node wins.

    Deliberately keeps trying after a pattern matches the *shape* but
    finds nothing: some refs are genuinely ambiguous across systems —
    "PR-42" is both an Azure DevOps pull request and a syntactically
    valid Jira issue key, and LINK_PATTERNS' ordering alone can only
    guess which was meant. Returning on the first shape match (the
    previous behaviour) meant a ref whose first-listed interpretation
    didn't exist was dropped even when a later one resolved cleanly."""
    for pattern, source_system, extractor in LINK_PATTERNS:
        match = pattern.match(target_ref)
        if not match:
            continue
        native_id = extractor(match)
        found = await node_repo.get_by_technical_identity_any_instance(source_system, native_id)
        if found is not None:
            return found
    return None


async def extract_links_for_node(
    node_repo: NodeRepository,
    edge_repo: EdgeRepository,
    connector: SourceConnector,
    *,
    from_node_id: UUID,
    from_native_id: str,
    from_kind: str,
    now: datetime,
) -> LinkExtractionStats:
    stats = LinkExtractionStats()
    links = await connector.get_links(from_native_id)
    rules = _relationship_rules()

    for link in links:
        target = await _resolve_target(node_repo, link.target_ref)
        if target is None:
            logger.info(
                "link_extraction.unresolved",
                from_native_id=from_native_id,
                target_ref=link.target_ref,
                source_system=connector.source_system,
            )
            stats.unresolved += 1
            continue

        # The reference resolved to a real node — raise it above its
        # extraction-time prior (see _RESOLUTION_BOOST). Capped at 1.0 so a
        # vendor's own structured field stays exactly 1.0.
        confidence = min(1.0, link.confidence + _RESOLUTION_BOOST)
        auto_confirmed = confidence >= _AUTO_CONFIRM_THRESHOLD
        # link.reverse means the vendor stated the relation from the far
        # end's point of view (see SourceLink.reverse) — the edge belongs
        # pointing at the node we're processing, not out of it.
        src_id, dst_id = (
            (target.id, from_node_id) if link.reverse else (from_node_id, target.id)
        )
        src_kind, dst_kind = (target.kind, from_kind) if link.reverse else (from_kind, target.kind)

        edge_type = _edge_type_for(link.link_kind)
        if not rules.allows(edge_type, src_kind, dst_kind):
            logger.warning(
                "link_extraction.relationship_rejected",
                from_native_id=from_native_id,
                target_ref=link.target_ref,
                edge_type=edge_type.value,
                src_kind=src_kind,
                dst_kind=dst_kind,
            )
            stats.rejected += 1
            continue

        edge_candidate = Edge(
            src_id=src_id,
            dst_id=dst_id,
            type=edge_type,
            origin=EdgeOrigin.SYNC_STRUCTURAL if auto_confirmed else EdgeOrigin.SYNC_EXTRACTED,
            state=EdgeState.ACTIVE if auto_confirmed else EdgeState.PROPOSED,
            confidence=confidence,
            attributes={"evidence": link.evidence} if link.evidence else {},
            first_seen_at=now,
            last_seen_at=now,
        )
        if await upsert_edge(edge_repo, edge_candidate):
            stats.edges_created += 1

    return stats
