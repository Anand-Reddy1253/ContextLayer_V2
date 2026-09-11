# ADR-006: Deterministic retrieval, no embeddings

## Status
Accepted

## Context
The original brief explicitly excludes vector embeddings, semantic search,
and LLM-generated summaries. Retrieval could otherwise easily drift toward
"put everything in a vector store and let similarity search sort it out,"
which would make results non-reproducible and would hide *why* a given
piece of evidence was returned — the opposite of what an org-wide context
graph needs when multiple teams, and eventually audits, depend on it.

## Decision
Scope resolution and context-pack compilation are entirely deterministic:
graph traversal (bounded by `configs/stage-contracts.yaml` slot specs) plus
an explicit scoring formula — edge distance, edge-type weight, capability
match, recency, origin weight (`HUMAN` > `SYNC_EXTRACTED` >
`SYNC_STRUCTURAL`/`RULE` where relevant) — computed in SQL and Python, no
model call anywhere in the retrieval path (`docs/RETRIEVAL.md`).

Given the same graph state and the same inputs, `get_context_pack` returns
the same pack. Every fact in a pack carries an `evidence_id` traceable to a
source node and version.

## Consequences
- Retrieval quality is bounded by how well the graph is built (sync
  correctness, human-authored bindings) rather than by embedding quality —
  this pushes effort toward getting the graph right, which is the actual
  problem being solved.
- Debugging a bad pack means reading the traversal and score, not
  re-running a similarity search and hoping.
- If semantic search is wanted later, it is a new component that consumes
  Context Fabric's graph as ground truth — it does not get retrofitted into
  this retrieval path.
