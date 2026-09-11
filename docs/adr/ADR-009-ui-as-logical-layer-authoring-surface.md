# ADR-009: UI as the logical-layer authoring surface

## Status
Accepted

## Context
The original scope list excluded a UI entirely. Working through the design,
the requester identified that the UI is not optional: it is where a human
builds the business hierarchy (org → division → tribe → squad → team) and
draws the links between that hierarchy and technical assets — the act that
turns a team name into a searchable boundary (ADR-001). Without a UI, that
authoring has to happen by hand-editing YAML, which does not scale past a
handful of teams in a 50+ team org.

Node/graph authoring specifically needs an interactive canvas — dragging a
business node onto a technical asset to propose a binding is materially
easier as a UI interaction than as structured text editing.

## Decision
Build a React + TypeScript + Vite SPA (`ui/`) as a first-class deliverable,
scoped deliberately narrow:

- **Authors:** business tree (org/division/tribe/squad/team) CRUD, and
  logical layer (`ContextSpace` + bindings + edges) authoring, including a
  review queue for `PROPOSED` (`SYNC_EXTRACTED`) edges.
- **Never authors:** technical-layer nodes. Repositories, work items,
  pages, PRs, etc. are strictly read-only in the UI — sync-owned, always.
- **Never writes to vendor sources.** The UI calls Context Fabric's own
  REST API (`docs/API.md`); it has no vendor credentials and no vendor API
  client of its own.

Interaction surfaces: React Flow (`@xyflow/react`) for the link-drawing
canvas, Cytoscape.js for read-only large-graph exploration, Tailwind +
shadcn/ui-pattern components for the rest (`docs/UI.md`).

## Consequences
- This is a deliberate, recorded deviation from the original "Do not
  implement: User interface" instruction (see ADR-001) — every other
  original exclusion (embeddings, semantic search, LLM summaries, graph
  DB, full connectors beyond ADO/GitHub, Kubernetes, microservices, event
  bus) still stands.
- The UI is scheduled last in the phase sequence (Phase 16) so the backend
  it depends on — catalog, graph, context-space APIs — exists first; it is
  not developed in parallel with an unstable backend contract.
- Because the UI never writes technical nodes, there is no risk of the UI
  becoming a second source of truth that sync then has to reconcile
  against.
