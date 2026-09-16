# ADR-011: LLM-inferred relationships as always-reviewed proposed edges

## Status
Accepted

## Context
`AGENTS.md §4` prohibits LLM-generated inference "ever, in any phase,"
outside one narrow exception. `ADR-010` already used that exception for
search-ranking abstracts and embeddings — but its own decision text scopes
that explicitly: *"never on `get_context_pack`, `resolve_scope`, or any
context-pack compilation path"* and, more specifically, to the
*search/discovery surface only*.

Tier 3 of the Confluence relationship-extraction work (Tiers 1/2 already
built, deterministic) is a genuinely different kind of claim: relationships
like "this ADR supersedes that one" or "this incident was caused by that
change" are stated in prose, not a structured macro or vendor field —
nothing deterministic in this codebase can find them. Producing them
requires a model. But a model-inferred **graph edge** is a different risk
than a model-inferred **search abstract**: an abstract that's slightly off
degrades a search result; a wrongly-inferred `SUPERSEDES` edge, if ever
treated as fact, actively misleads whoever reads the graph. `ADR-010`'s
scope doesn't cover this, and shouldn't be stretched to.

## Decision
LLM-inferred relationships are permitted, under a narrower, additional set
of guardrails than `ADR-010`'s:

1. **One model call per document, never a pairwise comparison.** The model
   reads exactly one document (plus a closed list of already-known service/
   product names given as context) and extracts what that document itself
   says it's about and what it references — it never compares two documents
   against each other. Relationship *discovery* between two specific
   documents happens afterward, deterministically (fuzzy title matching
   against already-synced document names), not via a second model call.
   This keeps the LLM cost at O(n) qualifying documents, never O(n²) pairs.
2. **Always `state=PROPOSED`, never auto-confirmed, regardless of
   confidence.** Deterministic Tier 1/2 edges auto-confirm above a
   confidence threshold because that confidence reflects *where* a
   vendor-declared reference was found (a title, a branch name) — a fact
   about the data. An LLM's self-reported confidence is not that; it is
   the model's own assessment of its own guess. No confidence value from
   this path ever bypasses human review.
3. **A new, distinct `EdgeOrigin.LLM_INFERRED`** — never conflated with
   `SYNC_EXTRACTED` (pattern-matched from vendor data). Anything that
   already branches on `EdgeOrigin` — a query, a reviewer's mental model —
   can tell "a regex found this" from "a model guessed this" without
   inspecting `attributes`.
4. **Every edge carries its own provenance** in `attributes`:
   `extracted_by`, `model`, and a short `rationale` — the literal hint text
   that led to the edge — shown directly in the Proposed Links review
   queue, not buried.
5. **Closed-vocabulary inputs only, validated post-hoc.** The model is
   only ever given a fixed list of already-known service/product names to
   choose from for the `services` extraction; anything it returns outside
   that list is dropped before an edge is ever proposed — the model cannot
   invent a target that doesn't already exist in the graph.
6. **Same boundary as `ADR-006`/`ADR-010`**: never touches
   `get_context_pack`, `resolve_scope`, or any context-pack compilation
   path. A `PROPOSED` edge sits in the review queue until a human acts on
   it; nothing here changes what any deterministic retrieval path sees.

## Consequences
- A third data-trust tier now exists alongside `HUMAN`/`RULE` (authored)
  and `SYNC_STRUCTURAL`/`SYNC_EXTRACTED` (vendor-derived, confidence-
  graduated): `LLM_INFERRED` (model-derived, always provisional). Anything
  that filters or reasons about `EdgeOrigin` should treat this as its own
  category, not a variant of `SYNC_EXTRACTED`.
- The review queue now needs to show *why* an edge exists in a way that
  differs by origin (a regex match snippet vs. a model's stated rationale)
  — `docs/UI.md`'s "Proposed links review queue" gets a note; the UI
  itself already has one flexible evidence-display slot to extend rather
  than needing a second one.
- Scoped to Confluence's already-classified documents (ADR/PostMortem/PRD/
  MeetingNotes, from the deterministic Tier 3 template classification) for
  now — extending this to other connectors' narrative text (a Jira
  description, an ADO work item) is a real possible future, not covered by
  this decision as written; it would need the same one-call-per-document,
  closed-vocabulary, always-`PROPOSED` treatment, not a shortcut.
