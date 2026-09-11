# Phase 15 — REST API consolidation

## Goal
Fill in `src/context_fabric/main.py` and every route group in
`docs/API.md`, wiring `retrieval/`, `catalog/`, `graph/`,
`synchronization/`, `authorization/` behind thin HTTP handlers. Mount the
Context MCP HTTP transport (Phase 12) on the same app.

## Inputs
- `docs/API.md` — every endpoint, exactly.
- Every package this phase exposes already exists and is tested from
  Phases 2-14; this phase is integration/exposure, not new business logic.

## Files to create
- `main.py` (replaces the Phase-0 placeholder) — FastAPI app assembly:
  CORS from `CF_CORS_ORIGINS`, route registration, MCP HTTP mount at a
  distinct path (e.g. `/mcp`), `/healthz` from Phase 14.
- `api/routes/org.py`, `connectors.py`, `catalog.py`, `graph.py`,
  `context_spaces.py` per `docs/API.md`'s table-by-table endpoint list.
- `api/deps.py` — shared FastAPI dependencies: DB session, actor identity
  extraction (`X-CF-Actor-Id` header, same mechanism `mcp/server_http.py`
  already uses per `docs/MCP.md` "Both transports resolve to the same
  actor_id... flow" — reuse it, don't reimplement).
- `api/errors.py` — problem-details error handler mapping `domain/errors.py`
  categories to HTTP status codes (`docs/API.md` "Errors").

## Acceptance criteria
- Every endpoint in `docs/API.md` exists, with the documented method,
  path, and request/response shape.
- `GET /api/connectors` never includes `credential_ciphertext` or a
  decrypted value in its response — checked with a dedicated test, not
  just eyeballed (`docs/SECURITY.md`).
- Every route applies `authorization.filter_visible` on any node data it
  returns — same exclusion-gate style test as Phase 11, run once at the
  API layer to confirm the REST surface isn't a side door around it
  (`docs/API.md` "Cross-cutting").
- `POST /api/context-spaces` + `POST /api/context-spaces/{id}/bindings`
  reproduces `configs/context-spaces/talentflow-identity.yaml`'s shape
  when called with equivalent input (round-trip proof the API matches
  `catalog/context_spaces.py`'s Phase-8 behavior exactly).

## Tests to write
`tests/integration/api/` — one file per route module, using FastAPI's
`TestClient`/`httpx.AsyncClient` against the real (test) database.

## Exit gate
`uvicorn context_fabric.main:app` starts cleanly; `pytest tests/integration/api -q`
green; `pytest tests/acceptance -q` (full suite so far) still green.
