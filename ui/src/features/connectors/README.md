# Connectors

Connection config screen: add a connector instance (source_system +
instance_id + non-secret config + credential), trigger a sync, watch
sync_run status, and view the resulting assets once complete. Secrets are
write-only from the UI's perspective — never returned by any read endpoint
(docs/SECURITY.md).

Calls `POST /api/connectors`, `POST /api/connectors/{id}/sync`,
`GET /api/connectors/{id}/sync-runs` (docs/API.md).

Implemented in Phase 16 (docs/phases/PHASE-16.md).
