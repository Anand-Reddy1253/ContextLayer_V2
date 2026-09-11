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
from re import Match
from uuid import UUID

import structlog

from context_fabric.connectors.base import SourceConnector
from context_fabric.domain.edge import Edge
from context_fabric.domain.enums import EdgeOrigin, EdgeState, EdgeType
from context_fabric.domain.node import Node
from context_fabric.persistence.repositories.edge import EdgeRepository
from context_fabric.persistence.repositories.node import NodeRepository
from context_fabric.synchronization.idempotency import upsert_edge

logger = structlog.get_logger()

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

# Extracted edges are proposals, not verified facts — confidence reflects
# that they came from automated pattern matching, not a human or the
# source's own structural hierarchy.
_EXTRACTED_CONFIDENCE = 0.7


_EDGE_TYPE_BY_LINK_KIND: dict[str, EdgeType] = {
    "mentions": EdgeType.MENTIONS,
    "relates_to": EdgeType.RELATED_TO,
    "verifies": EdgeType.VERIFIES,
    "depends_on": EdgeType.DEPENDS_ON,
}


def _edge_type_for(link_kind: str) -> EdgeType:
    return _EDGE_TYPE_BY_LINK_KIND.get(link_kind, EdgeType.RELATED_TO)


@dataclass
class LinkExtractionStats:
    edges_created: int = 0
    unresolved: int = 0


async def _resolve_target(node_repo: NodeRepository, target_ref: str) -> Node | None:
    for pattern, source_system, extractor in LINK_PATTERNS:
        match = pattern.match(target_ref)
        if match:
            native_id = extractor(match)
            return await node_repo.get_by_technical_identity_any_instance(source_system, native_id)
    return None


async def extract_links_for_node(
    node_repo: NodeRepository,
    edge_repo: EdgeRepository,
    connector: SourceConnector,
    *,
    from_node_id: UUID,
    from_native_id: str,
    now: datetime,
) -> LinkExtractionStats:
    stats = LinkExtractionStats()
    links = await connector.get_links(from_native_id)

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

        edge_candidate = Edge(
            src_id=from_node_id,
            dst_id=target.id,
            type=_edge_type_for(link.link_kind),
            origin=EdgeOrigin.SYNC_EXTRACTED,
            state=EdgeState.PROPOSED,
            confidence=_EXTRACTED_CONFIDENCE,
            attributes={"evidence": link.evidence} if link.evidence else {},
            first_seen_at=now,
            last_seen_at=now,
        )
        if await upsert_edge(edge_repo, edge_candidate):
            stats.edges_created += 1

    return stats
