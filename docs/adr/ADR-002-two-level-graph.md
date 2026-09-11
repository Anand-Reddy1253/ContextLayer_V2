# ADR-002: One node/edge schema in PostgreSQL, no dedicated graph database

## Status
Accepted

## Context
The domain is naturally graph-shaped — three layers of nodes connected by
typed, directional edges, queried by traversal ("everything under this
scope," "what does this work item depend on"). A dedicated graph database
(Neo4j, etc.) is the obvious reach, and was explicitly ruled out in the
original brief.

## Decision
Model the entire graph — business, technical, and logical layers — as one
`node` table and one `edge` table in PostgreSQL (`docs/persistence.md`),
distinguished by a `layer` column and an `origin` column on edges, rather
than three separate schemas or a separate database technology.

Traversal is recursive CTEs bounded by depth and edge-type filters
(`graph/traversal.py`), plus `ltree` for the "everything under this path"
containment queries that dominate scope resolution.

## Consequences
- **One place to apply authorization** (the repository query layer, ADR-007)
  instead of three or a cross-database join.
- **One search/index strategy** instead of keeping a graph DB and a
  relational DB in sync.
- **A ceiling exists.** Recursive CTEs over a few hundred thousand nodes
  with bounded hop counts are fine; multi-million-node, unbounded-depth
  traversal is not what this schema is optimized for. If that ceiling is
  ever hit, it is a new ADR, not a silent migration.
- Layer-specific validation (a BUSINESS node cannot have a `native_id`, a
  TECHNICAL node cannot be manually reparented) lives in the domain model
  and repository layer, not enforced by three separate table shapes.
