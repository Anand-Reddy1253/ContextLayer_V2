# Graph Canvas

Two distinct interactions, per the plan's UI-stack decision
(docs/UI.md "Graph Canvas"):

- **Link canvas** (@xyflow/react) — the human-authored linking surface:
  drag a business node onto a technical asset to propose a logical edge,
  used when authoring a ContextSpace's bindings.
- **Graph explorer** (cytoscape.js via react-cytoscapejs) — large
  read-only traversal view for browsing the compiled graph around a node.

Calls `GET /api/graph/*` for exploration and the context-spaces endpoints
(docs/API.md) for authoring writes.

Implemented in Phase 16 (docs/phases/PHASE-16.md).
