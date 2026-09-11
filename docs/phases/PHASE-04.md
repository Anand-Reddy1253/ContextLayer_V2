# Phase 4 — Azure DevOps fixture connector

## Goal
The reference connector implementation every later connector follows.
Native hierarchy: Project → Area Path → Epic → Feature → Story/Task/Bug,
plus Pull Requests and Builds.

## Inputs
- `docs/CONNECTORS.md` "Native hierarchies" and "Adding a new connector".
- `connectors/base.py` (Phase 3).
- `configs/context-spaces/talentflow-identity.yaml` — its ADO binding
  (`TalentFlow\Identity`) should resolve against these fixtures once sync
  exists (Phase 6), so build fixture data that makes that true.

## Files to create
- `connectors/azure_devops/mapper.py` — ADO REST API payload shapes ->
  `domain/` types. The only file allowed to know ADO's JSON shape.
- `connectors/azure_devops/fixture.py` — `AzureDevOpsFixtureConnector`
  implementing `SourceConnector` over `fixtures/azure_devops/*.json`.
- `connectors/azure_devops/live.py` — stub only in this phase: class
  skeleton implementing the Protocol, every method raising
  `NotImplementedError("live mode activated in Phase 19")`. No real HTTP
  code yet — that's explicitly deferred (`AGENTS.md` §4, "Optional live
  connector activation").
- `fixtures/azure_devops/*.json` — per `fixtures/azure_devops/README.md`'s
  planned layout: projects, area_paths, work_items/{epics,features,stories,bugs},
  pull_requests, builds, changes (incl. a tombstone), acl.

## Acceptance criteria
- `discover_containers()` returns the ADO project(s) in fixtures.
- `list_children()` walks Project → Area Path → Epic → Feature → Story
  correctly, paginated (at least one container has >1 page of children in
  the fixture data, per the README's pagination-boundary requirement).
- `get_changes()` returns at least one deletion; the mapped `SourceObject`
  has `deleted=True`.
- `get_links()` on at least one work item returns a link resolvable to
  another fixture object (proves the extraction path Phase 7 needs has
  real data to work with).
- Anti-leakage acceptance test (Phase 3) passes against this connector
  specifically — no ADO JSON shape crosses out of `mapper.py`.

## Tests to write
`tests/unit/connectors/azure_devops/test_mapper.py` — one test per mapped
type, asserting exact field translation from a sample ADO payload.
`tests/integration/connectors/test_azure_devops_fixture.py` — exercises
the connector's seven methods end-to-end against the real fixture files
(not mocked), including the pagination and tombstone cases.

## Exit gate
`pytest tests/unit/connectors/azure_devops tests/integration/connectors/test_azure_devops_fixture.py tests/acceptance/test_connectors_never_leak_vendor_shapes.py -q`
green.
