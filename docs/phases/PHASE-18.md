# Phase 18 — Docker Compose and documentation finalization

## Goal
Make `docker compose up` (the whole stack) work from a clean checkout, and
bring every doc back in sync with what was actually built (docs drift is
expected across 17 prior phases; this phase closes it).

## Inputs
- `docker-compose.yml`, `Dockerfile` (Phase 0) — now exercised for real by
  every service instead of just `postgres`.
- Every `docs/*.md` file — diff against actual code, not memory of the
  original plan.

## Activities
1. `docker compose up` brings up `postgres`, `api` (REST + MCP HTTP), and
   `ui` together; `api` waits on `postgres`'s healthcheck; run
   `make migrate` against the compose network (either as a one-shot
   `docker compose run` command added to the compose file, or documented
   as a manual step in `README.md` — pick one and make it consistent).
2. Reconcile documentation:
   - `docs/API.md` matches the real route list exactly (diff against
     `api/routes/`).
   - `docs/MCP.md` matches the real tool schemas exactly.
   - `docs/persistence.md` matches the real migration state exactly
     (`alembic history` vs. the doc's table list).
   - `docs/PROGRESS.md` shows every phase 1-17 as ✅ with real test
     commands and honest "unverified" entries (live-mode connectors are
     expected to still be unverified pending Phase 19).
   - `README.md`'s quickstart commands are run verbatim, once, to confirm
     they actually work as written.
3. Add a top-level `docker-compose.yml` `migrate` one-shot service or
   document the manual `make migrate` step clearly — whichever is chosen,
   `README.md` reflects it.

## Acceptance criteria
- A clean checkout, following only `README.md`, ends with a working UI at
  `localhost:5173` talking to a working API at `localhost:8000` backed by
  a migrated, synced Postgres — verified by literally doing this once.
- No doc references a file, endpoint, or table that doesn't exist; no
  existing file/endpoint/table is undocumented (spot-checked, not
  necessarily exhaustive for every field).

## Exit gate
`docker compose up -d && make migrate` (or the finalized equivalent) then
`context-fabric sync --source ado --fixture && context-fabric sync --source github --fixture`
then a browser check of all five UI screens, then `pytest -q` (the entire
suite) green.
