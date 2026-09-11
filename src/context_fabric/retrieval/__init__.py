"""Retrieval.

Deterministic scope resolution (task_ref -> context spaces -> products /
teams / services / repositories, docs/RETRIEVAL.md) and the context-pack
compiler that reads configs/stage-contracts.yaml and fills each slot by
traversal + ranking (edge distance, edge-type weight, capability match,
recency, origin weight) within a token budget.

No embeddings, no semantic search, no LLM calls (see docs/architecture.md
"Explicitly out of scope"). Ranking is entirely SQL + deterministic scoring
in Python.

Must never import connectors/ — retrieval only reads what synchronization/
already persisted through persistence/. Depends on domain/, persistence/,
graph/, authorization/, catalog/. Implemented in Phases 9-10
(docs/phases/PHASE-09.md, PHASE-10.md).
"""

from __future__ import annotations

from context_fabric.retrieval.scope import BindingCandidate, ScopeResolution, resolve_scope
from context_fabric.retrieval.task_ref import ParsedTaskRef, UnrecognizedTaskRef, parse_task_ref

__all__ = [
    "BindingCandidate",
    "ParsedTaskRef",
    "ScopeResolution",
    "UnrecognizedTaskRef",
    "parse_task_ref",
    "resolve_scope",
]
