# Phase 8 — Context-space mapping

## Goal
Implement the logical layer's persistence + write path: `ContextSpace` and
`Binding` CRUD, and the reconciliation command that maps declared bindings
onto whatever the technical layer currently contains.

## Inputs
- `docs/DOMAIN_MODEL.md` "ContextSpace", "Binding".
- `configs/context-spaces/talentflow-identity.yaml` as the worked example
  — this phase should be able to load it and produce the same
  `context_space`/`binding` rows a human would create via the (not yet
  built) UI form.
- `catalog/` package (create it now).

## Files to create
- `catalog/context_spaces.py` — `create_context_space`, `add_binding`,
  `update_binding`, `remove_binding`, `list_context_spaces` — domain-typed
  in, domain-typed out, backed by `persistence/repositories/`.
- `catalog/business_tree.py` — minimal business-node CRUD needed to give
  a `ContextSpace` somewhere to anchor (`business_node_id`) ahead of the
  full UI-driven version in Phase 16. Build the org tree for
  `configs/context-spaces/talentflow-identity.yaml`'s `business_ref`
  (`ACME/Engineering/TalentFlow/Identity`) as a fixture/seed, not
  hand-inserted SQL.
- `cli/main.py` addition: `context-fabric reconcile --context-space
  talentflow/identity` — loads the named context space's bindings,
  confirms each `native_container` actually resolves to synced technical
  nodes (from Phase 6-7's data), and reports mismatches (a binding
  pointing at a container that doesn't exist in the graph yet) rather than
  silently ignoring them.

## Acceptance criteria
- Loading `configs/context-spaces/talentflow-identity.yaml` via a
  one-time import script (or the reconcile command itself) produces a
  `context_space` row and 4 `binding` rows matching the file exactly.
- `reconcile` against a graph that has *not* yet synced GitHub reports the
  GitHub bindings as unresolved, clearly, not as a crash.
- After both connectors have synced (Phase 6-7), `reconcile` reports all
  4 bindings resolved.

## Tests to write
`tests/integration/catalog/test_context_spaces.py` — CRUD round trip;
`tests/integration/cli/test_reconcile.py` — the resolved/unresolved
reporting behavior described above, using the real
`talentflow-identity.yaml` fixture.

## Exit gate
`context-fabric sync --source ado --fixture && context-fabric sync --source github --fixture && context-fabric reconcile --context-space talentflow/identity`
reports all bindings resolved; `pytest tests/integration/catalog tests/integration/cli -q`
green.
