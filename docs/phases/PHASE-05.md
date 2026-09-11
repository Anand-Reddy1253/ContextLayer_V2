# Phase 5 — GitHub fixture connector

## Goal
Second connector, proving the abstraction from Phase 3-4 generalizes.
Native hierarchy: Organization → Repository → Branch → Directory → File,
plus Pull Requests, Commits, Actions runs.

## Inputs
- Same pattern as Phase 4, applied to GitHub. `connectors/azure_devops/`
  is the reference to follow, not to copy blindly — GitHub's hierarchy
  shape (tree-based, not area-path-based) is genuinely different, and the
  mapper should reflect that rather than forcing ADO's shape onto it.
- `configs/context-spaces/talentflow-identity.yaml`'s GitHub bindings
  (`acme-org/identity-service`, `acme-org/sso-gateway`) — fixture data
  should include both repos so the worked example resolves end-to-end
  after Phase 6.

## Files to create
- `connectors/github/mapper.py`, `connectors/github/fixture.py`,
  `connectors/github/live.py` (stub, same pattern as ADO's).
- `fixtures/github/*.json` per `fixtures/github/README.md`'s planned
  layout, including `acme-org/identity-service` and `acme-org/sso-gateway`.

## Acceptance criteria
Same shape as Phase 4's, adapted to GitHub's hierarchy:
`discover_containers` returns the org; `list_children` walks
Org → Repo → Branch → Directory → File with at least one paginated
boundary; `get_changes` includes a tombstone; `get_links` resolves at
least one PR-to-work-item or commit-to-work-item reference (e.g. a commit
message mentioning `AB#312`) — this is the cross-connector link Phase 7
needs to prove relationship extraction actually spans sources, not just
within one.
Anti-leakage test passes against this connector.

## Tests to write
Mirrors Phase 4: `tests/unit/connectors/github/test_mapper.py`,
`tests/integration/connectors/test_github_fixture.py`.

## Exit gate
`pytest tests/unit/connectors/github tests/integration/connectors/test_github_fixture.py tests/acceptance/test_connectors_never_leak_vendor_shapes.py -q`
green. Explicitly confirm both connectors now pass the shared anti-leakage
test in one run (not just individually) — this is the first point where
that matters.
