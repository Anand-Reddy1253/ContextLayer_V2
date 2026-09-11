# Phase 9 — Deterministic scope resolution

## Goal
Implement `docs/RETRIEVAL.md` §1 exactly: `task_ref` -> context spaces ->
products/teams/services/repositories, deterministic and fully traceable.

## Inputs
- `docs/RETRIEVAL.md` §1 "Scope resolution" and its ambiguity rules.
- `graph/traversal.py` (Phase 7), `catalog/context_spaces.py` (Phase 8).
- `authorization/` does not exist yet (Phase 11) — this phase builds scope
  resolution *without* authorization filtering wired in yet, but the
  function signature must already accept an `actor_id` and have an
  explicit, obvious seam where `filter_visible` gets called in Phase 11
  (a clearly marked pass-through, not a silent no-op that looks finished).

## Files to create
- `retrieval/scope.py` — `resolve_scope(task_ref, actor_id,
  context_space_override=None) -> ScopeResolution`, implementing the
  6-step algorithm and the 3-level ambiguity tiebreak from
  `docs/RETRIEVAL.md` §1.
- `retrieval/task_ref.py` — the per-source pattern table parsing
  `task_ref` strings (`"AB#312"` -> azure_devops work item) into a
  technical node lookup. Small and explicit — a new source's pattern is a
  one-line addition here, not a new parsing framework.

## Acceptance criteria
- `resolve_scope("AB#312", actor_id)` against the fully-synced +
  reconciled `talentflow/identity` fixture data returns the Identity
  Squad's context space, with `products=["talentflow"]`,
  `teams=["identity-squad"]`, `services=["identity-service", "sso-gateway"]`,
  and both GitHub repos in `repositories`.
- An ambiguous case (two overlapping bindings) is included in test fixture
  data specifically to exercise the longest-path-wins ->
  binding-priority -> binding-id tiebreak, and the result includes all
  candidates, not just the winner.
- A `task_ref` with no matching binding returns an explicit "unresolved"
  result, never a silent empty success that looks the same as "resolved to
  nothing in scope."

## Tests to write
`tests/integration/retrieval/test_scope_resolution.py` — the worked
example above, the ambiguity case, and the unresolved case, each as a
distinct test.

## Exit gate
`pytest tests/integration/retrieval/test_scope_resolution.py -q` green,
against the real fixture-synced database (not mocked graph data) — this
phase is the first point where retrieval logic runs against genuinely
synced+reconciled state end to end.
