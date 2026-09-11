# Phase 17 — Acceptance tests (consolidation)

## Goal
Every phase from 1-16 already wrote acceptance tests as it went
(idempotency in Phase 6, anti-leakage in Phase 3-5, authorization
exclusion in Phase 11, UI round-trip in Phase 16). This phase is not "write
acceptance tests for the first time" — it is: audit, consolidate, close
gaps, and make the full suite a single reliable command.

## Inputs
- Every `tests/acceptance/*.py` file written so far.
- `AGENTS.md` §3's ritual — this phase is where "the gates stay green" gets
  verified as a *suite*, not just phase-by-phase.

## Activities
1. Run `pytest tests/acceptance -q` as one suite; fix any interaction
   effects between tests that only surface when run together (shared
   fixture-database state, ordering dependencies).
2. Audit for gaps against the original brief's explicit requirements not
   yet covered by a named test:
   - Stage contracts are genuinely configuration-driven — add a test that
     adds a *new* stage to a copy of `stage-contracts.yaml` and confirms
     the compiler handles it with zero code changes (proves Phase 10's
     "generic, never special-cases a stage name" claim rather than just
     asserting it in a docstring).
   - `context-fabric reconcile` behavior on a context space with a
     deliberately broken binding (points at a native_container that will
     never resolve) reports it clearly rather than hanging or crashing.
   - Deletion/tombstone propagation: delete a node's underlying fixture
     data, re-sync, confirm the node is tombstoned *and* disappears from
     any context pack that previously included it.
3. Ensure `tests/acceptance/` test names remain self-describing per
   `docs/CONVENTIONS.md` "Test layout" (named after the gate, not a phase
   number) — rename anything that drifted.

## Acceptance criteria
- `pytest tests/acceptance -q` passes as a single run, from a clean
  database, deterministically (run it twice in a row to confirm no
  ordering flakiness).
- The three gap-audit items above each have a named test.
- `docs/PROGRESS.md` accurately reflects every acceptance gate's status.

## Exit gate
`docker compose up -d postgres && make migrate && pytest tests/acceptance -q`
green, twice in a row, from a freshly migrated database each time.
