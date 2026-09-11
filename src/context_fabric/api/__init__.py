"""REST API.

FastAPI routers consumed by ui/ (docs/API.md): business-tree CRUD,
connector connection config + sync trigger/status, catalog/asset browsing,
graph query endpoints, and context-space + logical-edge authoring.

This is the only package allowed to translate HTTP <-> domain objects.
Route handlers stay thin — they call catalog/, graph/, retrieval/,
synchronization/, authorization/ and shape the response; no business logic
lives in routes/.

Depends on retrieval/, catalog/, graph/, synchronization/, authorization/.
Implemented incrementally alongside the packages it exposes, consolidated in
Phase 15 (docs/phases/PHASE-15.md).
"""
