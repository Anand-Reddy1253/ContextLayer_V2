# Phase 16 — UI

## Goal
Build the five screens in `docs/UI.md` against the now-stable REST API
(Phase 15). This is the largest single phase and the first one requiring
Node — coordinate on `docker compose up -d ui` (Node install not required
on the host, `docker-compose.yml`'s `ui` service) or a local Node 22
install if available.

## Inputs
- `docs/UI.md` — full screen/component spec.
- `docs/API.md` — every endpoint this phase's screens call.
- `ui/` scaffold from Phase 0 (`package.json`, `tsconfig.json`,
  `vite.config.ts`, feature folder READMEs) — this phase fills those
  folders in; it does not restructure them without reason.

## Files to create (per `docs/UI.md`, one feature folder each)
- `ui/src/lib/api-client.ts` — typed fetch wrapper + react-query hooks
  matching `docs/API.md` exactly; `ui/src/lib/types.ts` mirroring
  `docs/DOMAIN_MODEL.md`'s shapes.
- `ui/src/features/org-tree/` — tree component, inline rename,
  drag-to-reparent, side panel.
- `ui/src/features/connectors/` — connection form (credential field
  write-only, never pre-filled on edit), sync trigger + live status
  polling.
- `ui/src/features/catalog-explorer/` — read-only browse + search.
- `ui/src/features/context-spaces/` — binding CRUD form, React Flow link
  canvas, proposed-edges review queue (confirm/reject/retype against
  `GET/POST /api/edges/*`).
- `ui/src/features/graph-canvas/` — Cytoscape.js read-only explorer.
- `ui/src/app/App.tsx`, `ui/src/app/router.tsx` — replaces the Phase-0
  placeholder shell with the real routed layout (left nav + top bar per
  `docs/UI.md` "Layout").

## Acceptance criteria
- Every "What the UI does not do" item in `docs/UI.md` is verifiably true:
  no technical-node edit path exists in the code; no vendor API is called
  from `ui/` (grep for any non-`/api` fetch target as a sanity check); no
  credential is ever pre-filled into a form after initial save.
- Creating a `ContextSpace` + bindings through the UI and then calling
  `context-fabric reconcile --context-space <id>` (Phase 8's CLI) reports
  the same resolved bindings as the manual YAML-driven flow did in Phase 8
  — proves the UI's writes are equivalent to the config-file path, not a
  parallel, divergent one.
- The proposed-edges review queue, after a human confirms one, causes that
  edge's `state` to flip to `ACTIVE` and it then appears in a
  `get_context_pack` result where it previously would have been excluded
  as `PROPOSED` (Phase 10's rule) — an end-to-end proof the UI action
  actually changes retrieval behavior.

## Tests to write
Component-level tests are optional for this PoC scope (not required by
`AGENTS.md`); the required proof is the two end-to-end acceptance
scenarios above, which can be written as `tests/acceptance/` tests calling
the REST API the way the UI does (not literal browser automation, unless
that's already set up) — `tests/acceptance/test_ui_context_space_roundtrip.py`
and `tests/acceptance/test_proposed_edge_confirmation_changes_pack.py`.

## Exit gate
`docker compose up -d ui` serves the app at `http://localhost:5173` without
console errors on each of the five screens; `npm run build` in `ui/`
succeeds; `pytest tests/acceptance -q` (full suite) green.
