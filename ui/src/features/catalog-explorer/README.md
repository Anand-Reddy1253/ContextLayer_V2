# Asset Catalog

UI label: "Asset Catalog" (internal/code identifiers unchanged). Read-only
browser over technical-layer assets synced from connectors: repositories,
work items, pages, PRs, etc., grouped by source and native hierarchy.
Never editable — technical nodes are sync-owned (docs/architecture.md
"Connector plane"). Calls `GET /api/catalog/*` (docs/API.md).

Implemented in Phase 16 (docs/phases/PHASE-16.md). See docs/UI.md
"Asset Catalog screen".
