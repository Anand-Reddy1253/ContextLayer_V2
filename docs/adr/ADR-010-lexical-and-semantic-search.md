# ADR-010: Lexical and semantic search on the discovery surface

## Status
Accepted

## Context
`AGENTS.md §4` prohibits vector embeddings, semantic search, and
LLM-generated summaries, "ever, in any phase." ADR-006 records why: retrieval
for `get_context_pack` must stay deterministic and auditable — same graph
state in, same pack out, every fact traceable to an evidence id — because
teams and audits depend on reproducing *why* something was returned.

`/api/catalog/search-cards` and `/api/catalog/search` are a different surface
from `get_context_pack`. Their own docstrings already say so — `search-cards`
is explicitly "a discovery/search surface, not [`expand_evidence`]"
(`docs/MCP.md`'s one-tool boundary). A human or an agent typing a keyword
query and getting a ranked list back is not the same operation as compiling
a deterministic, auditable context pack for a pipeline stage.

Investigating a real, reported search-quality problem this session surfaced
that ranking today is a 4-tier keyword bucket (`_score_match`, exact/prefix/
substring/description-substring) with ties broken by incidental row order —
already the diagnosed root cause of a real 29K-103K token blowup on one
query — and that `node.description` has been NULL on every technical node
since the schema was built, because `SourceObject`/`SourceContainer` never
had a `description` field. ADR-003 already lists `description` as intended
metadata; it was simply never wired up.

ADR-006 itself names the escape hatch: *"If semantic search is wanted later,
it is a new component that consumes Context Fabric's graph as ground
truth — it does not get retrofitted into this retrieval path."* This ADR
exercises exactly that option, on exactly the surface it names.

## Decision
On the **search/discovery surface only** (`/api/catalog/search-cards`,
`/api/catalog/search`, and any future MCP `search` tool) — never on
`get_context_pack`, `resolve_scope`, or any context-pack compilation path:

1. **Postgres full-text search** (`tsvector`/`ts_rank`/`pg_trgm`) replaces
   the 4-tier keyword scorer. This is lexical relevance ranking, not
   semantic search — permitted regardless, but named here since it directly
   touches the prohibited "reranking" territory in spirit.
2. **Selective LLM-generated abstracts**, only for node kinds whose name
   is not already self-descriptive and which have no vendor-supplied
   description (decided per-kind, evidence-based, not applied blanket —
   see the search-overhaul plan). Generated offline, stored as
   `attributes.llm_abstract` with a `description_origin` marker so
   vendor-sourced text always takes precedence and abstracts stay
   regenerable and auditable. Local model (Ollama), matching the runtime
   already chosen for the Intelligent Mapper classification work.
3. **pgvector semantic search**, additive to full-text (hybrid, reciprocal-
   rank fusion), only if measured (via a golden query set) to be needed
   after (1) and (2) — not built speculatively.

**`get_context_pack` stays exactly as ADR-006 requires**: deterministic
graph traversal + explicit scoring formula, no model call anywhere in that
path. This ADR does not touch it. `AGENTS.md §4` is amended with a pointer
to this ADR so the exception is discoverable from the rule itself, scoped
explicitly to search.

`ADR-003` (selective materialization) is unaffected for vendor-sourced
`description` (already within its "metadata" list) and is clarified, not
amended, for LLM abstracts: they are a bounded, hard-capped, plain-text
derived field — never a stored body — regenerable from source, same spirit
as everything else ADR-003 already governs.

## Consequences
- Two different retrieval philosophies now coexist by design: deterministic
  for `get_context_pack` (auditable, reproducible), ranked/probabilistic for
  search (helpful, not audit-grade). Anyone extending either path must know
  which one they're in — `docs/MCP.md` and `docs/RETRIEVAL.md` get a note
  making this explicit.
- LLM abstracts introduce the project's first non-deterministic, model-
  dependent stored field. Mitigated by the `description_origin` marker
  (always inspectable, always regenerable, never authoritative over vendor
  data) and by running generation offline rather than in the request path.
- If search quality plateaus without pgvector, it is never built — (3) is
  gated on evidence, not committed to now.

## Amendment: (3) built without pgvector

`pgvector` is not available on this deployment's Postgres install (`vector`
returns zero rows from `pg_available_extensions`), and unlike Ollama there's
no simple installer for it on Windows. Rather than block step (3) on that,
embeddings (Confluence pages only, via `nomic-embed-text` — same local
Ollama runtime as the abstracts in (2)) are stored as a plain JSONB float
array on `node.attributes.embedding`, and similarity is computed in Python
(`retrieval/semantic.py`'s `cosine_similarity`/`reciprocal_rank_fusion`)
rather than in SQL. Fine at the current scale (a few dozen embedded nodes);
an O(n) Python scan stops being fine well before pgvector would need
installing anyway, and nothing about the `/search-cards?semantic=true`
contract would need to change if it's swapped in later — only this one
module. Still additive/opt-in, still hybrid RRF, still never touching
`get_context_pack` — the "how" changed, not the "what" or "why."
