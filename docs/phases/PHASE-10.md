# Phase 10 — Context-pack compiler and stage contracts

## Goal
Implement `docs/RETRIEVAL.md` §2-4: the generic stage-contract compiler,
ranking, and token budgeting, producing a real `ContextPack`.

## Inputs
- `configs/stage-contracts.yaml` — all five stages already fully specified.
- `retrieval/scope.py` (Phase 9), `graph/traversal.py` (Phase 7).
- Note: this phase still runs *without* authorization filtering wired in
  (Phase 11) — same seam requirement as Phase 9: the compiler must call
  through an obvious, single choke point that Phase 11 fills in, not
  something that has to be threaded through every function afterward.

## Files to create
- `retrieval/contracts.py` — loads/validates
  `configs/stage-contracts.yaml` into `domain/config.py` types (Phase 1),
  applies `defaults` for omitted slot fields.
- `retrieval/ranking.py` — the scoring formula from
  `docs/RETRIEVAL.md` §3, with weights as named constants pulled from
  config (not hardcoded inline).
- `retrieval/budget.py` — the token-share allocation and truncation ->
  `expansion_handle` logic from §4 (character-count/4 estimator,
  documented as an approximation).
- `retrieval/compiler.py` — `compile_context_pack(task_ref, stage,
  actor_id, token_budget, repo_sha=None) -> ContextPack`. Generic over
  stage name — must not contain any `if stage == "implementation"`
  branching; slot behavior comes entirely from the loaded contract.

## Acceptance criteria
- Every one of the five stages (`requirement`, `design`, `implementation`,
  `testing`, `review`) compiles a pack against the fixture-synced data
  without raising, for at least one real `task_ref` from the fixtures.
- A `required: true` slot that ends up empty appears in `conflicts` or
  `open_questions` — write a fixture scenario that deliberately triggers
  this (e.g. a work item with no linked design document) and assert on it.
- Every item in every populated slot carries an `evidence_id` present in
  the pack's `evidence` list — checked generically (iterate every slot,
  not per-stage-hardcoded assertions).
- Token budget truncation actually produces `expansion_handles` when a
  small budget is given, verified by compiling the same pack with a large
  and a small budget and diffing.

## Tests to write
`tests/integration/retrieval/test_compiler.py` — one test per stage using
real synced data, plus the required-slot-empty and token-budget-truncation
cases above. `tests/unit/retrieval/test_ranking.py`,
`test_budget.py` — pure-function tests with hand-built candidate lists.

## Exit gate
`pytest tests/integration/retrieval/test_compiler.py tests/unit/retrieval -q`
green.
