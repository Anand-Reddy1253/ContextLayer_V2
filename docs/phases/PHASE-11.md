# Phase 11 — Authorization filtering

## Goal
Fill the seam Phases 9-10 left open: real `AuthorizationService`, wired in
at the repository query layer, before ranking and compilation, everywhere
(ADR-007). Prove the negative case.

## Inputs
- `docs/SECURITY.md` — full spec.
- `fixtures/authz/` (README already describes the planned shape) — write
  the real `actors.yaml`/`acl_grants.yaml` now, including at least one
  actor deliberately excluded from at least one acl_ref referenced by the
  ADO/GitHub fixture data.

## Files to create
- `authorization/service.py` — `AuthorizationService` Protocol,
  `can_read(actor, acl_ref)`, `filter_visible(actor, nodes)`.
- `authorization/fixture.py` — implementation reading
  `fixtures/authz/*.yaml`.
- `fixtures/authz/actors.yaml`, `fixtures/authz/acl_grants.yaml` — real
  content, including the deliberate-exclusion case above.
- Wire `filter_visible` into the exact seams left in `retrieval/scope.py`
  (Phase 9) and `retrieval/compiler.py`/traversal calls (Phase 10), and
  into `persistence/repositories/` query methods where nodes are read for
  any retrieval or catalog purpose.

## Acceptance criteria — the exclusion gate
An actor lacking the grant for a specific acl_ref:
- Never sees that node/evidence in `resolve_scope` output.
- Never sees it in any `get_context_pack` slot, even when it would
  otherwise be the highest-ranked candidate for a `required` slot (in
  which case the slot correctly reports empty/conflict, per Phase 10's
  rule — it does not fall back to the next-best *unauthorized* item).
- Context-space membership alone (being listed in a `ContextSpace`'s
  `teams`/`owners`) does not grant access to a node whose `acl_ref` the
  actor isn't separately permitted for — write a fixture case that proves
  this specifically, not just implies it.

## Tests to write
`tests/acceptance/test_unauthorized_evidence_excluded_from_pack.py` — the
gate above, using the real fixture data and a real compiled pack, not a
mocked authorization service. This is a permanent gate (`AGENTS.md` §3),
alongside the Phase 6 idempotency gate.

## Exit gate
`pytest tests/acceptance/test_unauthorized_evidence_excluded_from_pack.py -q`
green, plus a full re-run of every acceptance test written so far
(`pytest tests/acceptance -q`) to confirm authorization wiring didn't
regress idempotency or anti-leakage.
