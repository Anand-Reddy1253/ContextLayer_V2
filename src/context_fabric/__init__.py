"""Context Fabric.

A context graph over three layers — business (org structure), technical
(connector-sourced source hierarchies), and logical (human-authored bindings
between the two) — served as search, MCP, and a UI.

See docs/architecture.md for the full design and docs/AGENTS.md-adjacent
docs/phases/ for the implementation sequence. This package ships no behavior
until Phase 1 (docs/phases/PHASE-01.md) lands.

Subpackage dependency direction (enforced by convention, checked in review —
see docs/CONVENTIONS.md "Layer boundaries"):

    domain          <- depended on by everything; depends on nothing in this package
    persistence     -> domain
    connectors      -> domain
    synchronization -> domain, persistence, connectors, graph
    catalog         -> domain, persistence
    graph           -> domain, persistence
    authorization   -> domain, persistence
    retrieval       -> domain, persistence, graph, authorization, catalog
    observability   <- depended on by everything; depends on nothing in this package
    api             -> retrieval, catalog, graph, synchronization, authorization
    mcp             -> retrieval, catalog, authorization
    cli             -> synchronization, connectors, retrieval

retrieval/ must never import connectors/ — retrieval reads only what sync
already persisted. connectors/ must never import api/, mcp/, retrieval/,
or graph/ — a connector's only job is to produce domain objects.
"""
