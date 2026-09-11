# Phase 6 — Idempotent synchronization

## Goal
Wire connectors → domain → persistence into a real sync pipeline, with the
CLI to drive it, and prove idempotency.

## Inputs
- `docs/architecture.md` §4 "Sync data flow".
- `connectors/registry.py` (Phase 3), both fixture connectors (Phases 4-5),
  `persistence/repositories/` (Phase 2).

## Files to create
- `synchronization/orchestrator.py` — the pipeline: discover_containers ->
  BFS list_children (respecting cursors) -> map -> content_hash diff ->
  upsert node -> structural CONTAINS edges -> get_changes tombstone sweep.
  Link extraction (`get_links`) is scoped to Phase 7, not this phase —
  this phase creates structural edges only.
- `synchronization/idempotency.py` — the content_hash comparison and
  upsert-or-skip logic, isolated so Phase 7 can reuse it for extracted
  edges too.
- `synchronization/state.py` — reads/writes `sync_state`, creates a
  `sync_run` row per invocation with a correlation ID.
- `cli/main.py` (fills in the Phase-0 placeholder) — Typer app:
  `context-fabric sync --source {ado|github} --fixture`,
  `context-fabric sync --source {ado|github} --live` (calls the Phase-4/5
  `live.py` stub, which will raise `NotImplementedError` until Phase 19 —
  that's expected and correct behavior for this phase).

## Acceptance criteria — the idempotency gate
Running `context-fabric sync --source ado --fixture` twice in a row
against a freshly migrated database produces:
- Identical node/edge counts after both runs.
- Zero `INSERT`/`UPDATE` statements attributable to unchanged objects on
  the second run (verified via `content_hash` comparison, not by
  disabling writes).
- `sync_run` shows two runs; the second run's `nodes_upserted` and
  `edges_created` are 0 for anything already correct from the first run.

This is a permanent gate, not a one-time check (`AGENTS.md` §3) — the test
proving it stays in `tests/acceptance/` and must stay green through every
later phase.

## Tests to write
`tests/acceptance/test_sync_is_idempotent.py` — the gate above, for both
connectors. `tests/integration/synchronization/test_orchestrator.py` —
pagination is actually followed to completion, tombstones set
`deleted_at` (not hard-delete), `sync_state.cursor` advances correctly.

## Exit gate
`docker compose up -d postgres && make migrate && context-fabric sync --source ado --fixture && context-fabric sync --source github --fixture && pytest tests/acceptance/test_sync_is_idempotent.py tests/integration/synchronization -q`
green.
