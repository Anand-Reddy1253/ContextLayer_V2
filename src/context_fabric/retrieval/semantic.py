"""Cosine similarity + reciprocal rank fusion for the opt-in `semantic=true`
path on `/search-cards` (`api/routes/catalog.py`).

Pure functions, no DB/HTTP — unit-testable without Postgres or Ollama, same
spirit as `retrieval/query_compiler.py`. No pgvector: it isn't available on
this deployment's Postgres install (see `docs/adr/ADR-010-...md`'s
amendment), so embeddings live as plain JSONB float arrays on
`node.attributes` and similarity is computed here, in Python, over whatever
small candidate set the caller fetched — fine at the current handful of
embedded nodes; swap in pgvector later without touching this module's
callers if that stops being true.
"""

from __future__ import annotations

import math
from uuid import UUID


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """1.0 = identical direction, 0.0 = orthogonal, -1.0 = opposite.
    0.0 (not an error) for a zero-length vector on either side — a
    genuinely empty embedding shouldn't crash a ranking pass, just score
    as unrelated to everything."""
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


# Below this, a result is noise, not a weak match — calibrated against
# real data (nomic-embed-text, query "vacancy bug" against 574 real
# embedded nodes): genuine matches landed at 0.69-0.72, unrelated ones at
# 0.28-0.33, median 0.50. 0.55 sits cleanly in the gap. This is an
# absolute floor, not a relative one, which matters specifically because
# of how reciprocal_rank_fusion works below: RRF only ever looks at
# *rank position*, never the underlying similarity score, so without this
# filter the least-bad of 574 irrelevant nodes would still rank #1 for a
# query nothing actually matches — found live ("vacancy bug" before this
# fix returned 100 results, the "best" of which was still just noise).
MIN_SIMILARITY = 0.55


def rank_by_similarity(
    query_vec: list[float],
    candidates: list[tuple[UUID, list[float]]],
    *,
    min_similarity: float = MIN_SIMILARITY,
) -> list[UUID]:
    """Candidate node ids above `min_similarity`, best-match first."""
    scored = [
        (node_id, sim)
        for node_id, vec in candidates
        if (sim := cosine_similarity(query_vec, vec)) >= min_similarity
    ]
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return [node_id for node_id, _score in scored]


def reciprocal_rank_fusion(rankings: list[list[UUID]], *, k: int = 60) -> dict[UUID, float]:
    """Standard RRF: `sum(1 / (k + rank))` across every ranking a node
    appears in (1-indexed rank), 0 contribution from a ranking it's absent
    from — so a node found by only one of several rankers still surfaces,
    just lower, rather than being excluded outright. `k=60` is the usual
    default in RRF literature (dampens the gap between rank 1 and rank 2
    without needing per-ranker score normalization, which lexical
    `_score_match` floats and cosine similarity aren't on the same scale
    for anyway)."""
    fused: dict[UUID, float] = {}
    for ranking in rankings:
        for rank, node_id in enumerate(ranking, start=1):
            fused[node_id] = fused.get(node_id, 0.0) + 1.0 / (k + rank)
    return fused
