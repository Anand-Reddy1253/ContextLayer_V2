# Azure DevOps fixtures

Deterministic JSON payloads shaped like real ADO REST API responses, used
by `connectors/azure_devops/` in fixture mode (Phase 4,
[../../docs/phases/PHASE-04.md](../../docs/phases/PHASE-04.md)) and by
`tests/acceptance/`. No live credentials or network calls involved.

Planned files (populated in Phase 4):

```
fixtures/azure_devops/
├── projects.json              # discover_containers() response
├── area_paths.json
├── work_items/
│   ├── epics.json
│   ├── features.json
│   ├── stories.json
│   └── bugs.json
├── pull_requests.json
├── builds.json
├── changes.json                # get_changes() delta pages, incl. a tombstone
└── acl.json                    # get_acl_reference() responses, paired with fixtures/authz/
```

Fixtures must include at least one deletion/tombstone case and one
pagination boundary (a container whose children span more than one page) so
the acceptance tests in `tests/acceptance/` can exercise both.
