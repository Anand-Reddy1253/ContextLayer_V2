# GitHub fixtures

Deterministic JSON payloads shaped like real GitHub REST/GraphQL responses,
used by `connectors/github/` in fixture mode (Phase 5,
[../../docs/phases/PHASE-05.md](../../docs/phases/PHASE-05.md)) and by
`tests/acceptance/`. No live credentials or network calls involved.

Planned files (populated in Phase 5):

```
fixtures/github/
├── organizations.json         # discover_containers() response
├── repositories.json
├── branches.json
├── tree/
│   └── <repo>.json            # directory/file listing per repo
├── pull_requests.json
├── commits.json
├── actions_runs.json
├── changes.json                # get_changes() delta pages, incl. a tombstone
└── acl.json                    # get_acl_reference() responses, paired with fixtures/authz/
```

Include at least one repo referenced by `configs/context-spaces/talentflow-identity.yaml`
(`acme-org/identity-service`, `acme-org/sso-gateway`) so the worked example
resolves end-to-end once sync is implemented.
