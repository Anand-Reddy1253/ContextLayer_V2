# Phase 7 — Native hierarchy and explicit relationship extraction

## Goal
Beyond structural `CONTAINS` edges (Phase 6), extract *actual lineage*
relationships from `get_links()` output: mentions and explicit references
that turn into `MENTIONS`/`RELATED_TO` edges (docs/architecture.md §5).

## Inputs
- `docs/architecture.md` §5 "Actual lineage vs. structural containment".
- The link data planted in Phase 4-5 fixtures (a work item mentioned in a
  commit message, a document referencing an ADO work item, etc.).
- `graph/` package (create it now — Phase 6 didn't need traversal, this
  phase's link *resolution* does).

## Files to create
- `synchronization/link_extraction.py` — for each synced object, calls
  `get_links()`, parses each `SourceLink.target_ref` against a small
  per-source pattern table (e.g. `AB#(\d+)` -> ADO work item id,
  `PROJ-(\d+)` -> Jira-shaped ref for future use), attempts to resolve it
  to an existing `node` row.
  - Resolves -> create edge with `origin=SYNC_EXTRACTED`,
    `type=MENTIONS` (or `RELATED_TO` if the link_kind says so),
    `state=PROPOSED` (a human confirms/retypes it later in the UI,
    `docs/UI.md` "Proposed links review").
  - Doesn't resolve -> park in a small `unresolved_link` table/log (not a
    hard failure) so a later sync pass or a UI surface can retry.
- `graph/traversal.py` — bounded recursive-CTE traversal
  (`edge_types`, `max_hops`, `direction`) and the ltree ancestor/descendant
  query helpers `docs/RETRIEVAL.md` describes. Built now because link
  resolution needs "does a node exist under this path" style lookups, and
  Phase 9 needs the same primitives — build once, correctly.

## Acceptance criteria
- At least one cross-connector edge exists after syncing both ADO and
  GitHub fixtures (e.g. a GitHub commit `MENTIONS` an ADO work item) —
  proves extraction isn't accidentally source-siloed.
- Extracted edges are `state=PROPOSED`, never `ACTIVE`, until a human (or
  a future auto-promotion rule, not built here) changes that.
- Re-running sync does not duplicate extracted edges (idempotency,
  `ux_edge_identity` on `(src_id, dst_id, type, origin)`).
- Traversal respects `max_hops` and `edge_types` filters exactly — tested
  with a hand-built small graph fixture, not just the real sync data.

## Tests to write
`tests/integration/synchronization/test_link_extraction.py`,
`tests/integration/graph/test_traversal.py` (hand-built graph,
deterministic hop counts and filters). Placed under `tests/integration/`,
not `tests/unit/graph/` as originally sketched — traversal runs a
recursive CTE against a real Postgres connection, and
`docs/CONVENTIONS.md`'s "unit tests have zero I/O" rule takes precedence
over the Phase 0 guess.

## Exit gate
`pytest tests/integration/synchronization/test_link_extraction.py tests/integration/graph -q`
green, plus a re-run of `tests/acceptance/test_sync_is_idempotent.py` to
confirm extraction didn't break the Phase 6 gate.
