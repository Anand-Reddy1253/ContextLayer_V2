# Phase 2 — PostgreSQL schema and migrations

## Goal
Stand up the real schema from `docs/persistence.md` via Alembic, and the
`persistence/` repository layer that is the *only* code allowed to touch
SQLAlchemy directly.

## Inputs
- `docs/persistence.md` — exact DDL for every table.
- `domain/` (Phase 1) — the Pydantic types repositories translate to/from.
- `docker-compose.yml`'s `postgres` service.

## Files to create
- `alembic.ini` (repo root), `migrations/env.py` (async engine, reads
  `CF_DATABASE_URL` from environment — never hardcoded), `migrations/versions/*`
  per the sequence sketched in `migrations/README.md`.
- `persistence/session.py` — async engine + session factory from
  `settings.CF_DATABASE_URL`.
- `persistence/orm/` — SQLAlchemy 2.x mapped classes: `Node`, `Edge`,
  `Evidence`, `ContextSpace`, `Binding`, `SyncState`, `SyncRun`,
  `TaskCheckpoint`, `ConnectorConnection`. One module per table, mirroring
  `docs/persistence.md` column-for-column.
- `persistence/repositories/` — `NodeRepository`, `EdgeRepository`,
  `EvidenceRepository`, `ContextSpaceRepository`, `SyncStateRepository`,
  `TaskCheckpointRepository`, `ConnectorConnectionRepository`. Each method
  takes/returns `domain/` types only, never an ORM object, to the outside.

## Acceptance criteria
- `docker compose up -d postgres && make migrate` succeeds from empty.
- Every table, column, type, and index in `docs/persistence.md` exists
  exactly as specified after migration.
- `ux_node_technical_identity` and `ux_edge_identity` uniqueness is
  verified by a test that inserts a duplicate and expects a constraint
  violation, not application-level dedup logic silently swallowing it.
- Repository methods never return an ORM object — verified by a type-level
  check or a runtime assertion in tests.

## Tests to write
`tests/integration/persistence/` — one file per repository, run against
the real Postgres from `docker compose up -d postgres`. Cover: CRUD round
trip preserving all fields, the two uniqueness constraints, soft-delete
(`deleted_at`) behavior, and `path` (ltree) ancestor/descendant queries
with a small hand-built tree fixture.

## Exit gate
`docker compose up -d postgres && make migrate && pytest tests/integration/persistence -q`
green. `alembic downgrade base && alembic upgrade head` round-trips
cleanly (proves migrations are reversible/rerunnable, not just
forward-tested once).
