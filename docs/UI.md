# UI

React 19 + TypeScript + Vite SPA (`ui/`), scoped per ADR-009: authors the
business and logical layers, browses the technical layer read-only. Never
writes to a vendor source directly — every write goes through Context
Fabric's own REST API (`docs/API.md`). Implemented in Phase 16
(`docs/phases/PHASE-16.md`), after the API surfaces it depends on exist.

## Stack

- **React 19 + TypeScript**, Vite dev server / build.
- **@tanstack/react-query** for all server state — no separate global
  store duplicating API data.
- **zustand** for local UI-only state (selected node, open panel, draft
  binding being drawn).
- **@xyflow/react (React Flow)** — the link-authoring canvas.
- **cytoscape.js + react-cytoscapejs** — read-only large-graph exploration.
- **Tailwind CSS**, shadcn/ui-pattern components copied into
  `src/components/` (not installed as a package, so they stay editable).
- **react-router-dom** for the top-level screens.

No Node install is required on a contributor's host — `docker compose up -d
ui` runs the dev server in a container (`docker-compose.yml`'s `ui`
service) against a bind-mounted `ui/`.

## Screens

### 0. Search (`features/search/`)

The default landing screen. A topic search over every synced TECHNICAL
node (`GET /api/catalog/search-cards`), plus an optional "scope to a
team/squad" filter (`business_node_id`) — restricted to what that
business node's own context space bindings structurally cover
(`CONTAINS`/`HAS_CONTEXT_SPACE`/`BINDS` edges only; a real authorization-
based filter is Phase 11's job, this is a manual stand-in). Results are
"cards": the matched node, its ancestor chain (repo/project/org it lives
under), and every direct cross-system link in both directions (a PR
mentioning a work item, a doc mentioning a repo, ...). Every node on a
card — match, ancestor, or linked node — carries a `locator`
(source_system/native_id/url), a deliberate departure from docs/MCP.md's
"one Context MCP server, vendor connectors never exposed" design:
this endpoint hands enough identity to the calling agent that its own
already-configured native per-vendor MCP servers (GitHub's, Atlassian's,
...) can read the full object directly — `expand_evidence` (Phase 12)
remains the path when no native MCP server is available. Ranking is
keyword/name+description matching for now; embeddings-based semantic
search over the same two short fields is a planned upgrade, not built
yet.

### 1. Business Hierarchy (`features/org-tree/`)

The business layer editor. A collapsible tree (org → division → tribe →
squad → team), inline rename, drag-to-reparent, and a side panel for
owners/description/product/service assignment on the selected node. Calls
`/api/org/*`.

### 2. Connectors (`features/connectors/`)

"One page which takes the connector details and saves in DB" — add a
connection (source system, instance id, config, credential), trigger a
sync, watch its `sync_run` status live (polling `/api/connectors/{id}/sync-runs`
via react-query), and jump to Asset Catalog filtered to what that run
produced once it completes. Credential fields are write-only inputs —
never pre-filled or displayed after save (`docs/SECURITY.md`).

### 3. Asset Catalog (`features/catalog-explorer/`)

Read-only browser over synced technical assets, grouped by source and
native hierarchy (ADO project/area path tree, GitHub org/repo/path tree).
Search box hits `/api/catalog/search`. Selecting a node shows its metadata,
evidence links (deep links back to the vendor), and a "view in graph"
action into the Graph Canvas.

### 4. Team Contexts (`features/context-spaces/`)

The core logical-layer authoring screen:

- Pick or create a `ContextSpace`, anchored to a business node.
- **Binding editor**: for each SDLC capability (`configs/capabilities.yaml`),
  pick a connector instance and a native container (autocompleted from
  Asset Catalog's data) — this is the CRUD form version of
  `configs/context-spaces/talentflow-identity.yaml`.
- **Link canvas** (React Flow): drag a business node onto a technical
  asset to propose a binding visually instead of filling the form; both
  paths write the same `binding` row via `/api/context-spaces/{id}/bindings`.
- **Proposed links review queue**: lists `SYNC_EXTRACTED` / `PROPOSED`
  edges (`GET /api/edges/proposed`) with confirm / reject / retype actions.
  This is where extracted `MENTIONS` edges get promoted to real
  relationships like `IMPLEMENTS` by a human.

### 5. Graph Canvas (`features/graph-canvas/`)

Cytoscape.js exploration: pick a starting node, choose edge types and hop
depth, render the neighborhood. Read-only — this is a debugging/
understanding tool for humans, not an editing surface (that's screen 4).
Also reachable from Asset Catalog's "view in graph" action.

## Layout

Left nav across the five screens above, a top bar showing the current
actor identity and (once a context space is selected) the active scope —
so a person can see exactly what boundary they're viewing or editing, the
same boundary an agent would resolve via `resolve_scope`.

## What the UI does not do

Edit technical-layer nodes. Show or accept vendor credentials anywhere but
the write-only Connectors form. Call a vendor API directly — always through
`/api/*`. Render an embedding/similarity search box — search is metadata
search only (`/api/catalog/search`, ADR-006).

## Dev workflow

```bash
docker compose up -d ui       # http://localhost:5173, proxies /api -> :8000
# or, with a local Node 22 install:
cd ui && npm install && npm run dev
```

Production build (`npm run build`) emits `ui/dist/`, served as static files
by the `api` image in `main.py` (Phase 15/18) — no separate UI server in
production, one deployable unit alongside the API.
