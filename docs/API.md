# REST API

The surface `ui/` consumes. Implemented incrementally alongside the
packages each route group exposes, consolidated in Phase 15
(`docs/phases/PHASE-15.md`). Route handlers stay thin — see
`src/context_fabric/api/__init__.py`.

All endpoints are versioned under `/api` and return JSON. Write endpoints
exist **only** for the business and logical layers — technical-layer data
is exposed read-only, always (ADR-009).

## Org (business layer) — `api/routes/org.py`

| Method | Path | Notes |
|---|---|---|
| GET | `/api/org/tree` | Full business tree, or `?root=<node_id>` for a subtree |
| POST | `/api/org/nodes` | Create a business node (org/division/tribe/squad/team/product/service) |
| PATCH | `/api/org/nodes/{id}` | Rename, re-describe, reassign owners |
| POST | `/api/org/nodes/{id}/reparent` | Move under a new parent (drag-to-reparent in the UI) |
| DELETE | `/api/org/nodes/{id}` | Soft-delete (`deleted_at`); refuses if a `ContextSpace` still references it |

## Connectors — `api/routes/connectors.py`

| Method | Path | Notes |
|---|---|---|
| GET | `/api/connectors` | List connector connections (credentials never included) |
| POST | `/api/connectors` | Create a connection: `source_system`, `instance_id`, `display_name`, `mode`, `config`, `credential` (write-only field, encrypted at rest — `docs/SECURITY.md`) |
| PATCH | `/api/connectors/{id}` | Update config; `credential` optional, replaces if provided |
| DELETE | `/api/connectors/{id}` | |
| POST | `/api/connectors/{id}/sync` | Trigger a sync run (`cli`'s `context-fabric sync` under the hood) |
| GET | `/api/connectors/{id}/sync-runs` | History from `sync_run`, paginated |
| GET | `/api/connectors/{id}/sync-runs/{run_id}` | One run's detail/status |

## Catalog (technical layer, read-only) — `api/routes/catalog.py`

| Method | Path | Notes |
|---|---|---|
| GET | `/api/catalog/nodes/{id}` | One technical node + its evidence refs |
| GET | `/api/catalog/nodes/{id}/children` | Native-hierarchy children, paginated |
| GET | `/api/catalog/search` | `?q=&source_system=&kind=&capability=` — metadata search, no embeddings (ADR-006) |

### Entity query

A structured alternative to `/search`, which can only AND a handful of scalar
params. Grammar lives in `domain/query.py`, compiled to SQL by
`retrieval/query_compiler.py`. Deliberately modelled on Port.io's search syntax
so an agent that knows that dialect can use this one.

| Method | Path | Notes |
|---|---|---|
| POST | `/api/catalog/entities/search` | `{query, limit}` — rule grammar; returns the lean shape below |
| POST | `/api/catalog/entities/aggregate` | `{query, group_by[]}` — live GROUP BY, no precomputed aggregates |
| GET | `/api/catalog/schema` | `?kind=` — queryable kinds, their attribute keys, relation types |

```jsonc
{"combinator": "and", "rules": [
  {"property": "$blueprint", "operator": "=",  "value": "STORY"},
  {"property": "state",      "operator": "!=", "value": "Done"},
  {"relation": "VERIFIES", "operator": "notRelatedTo", "value": "324"}]}
```

Properties are `$`-prefixed meta-properties (`$title`, `$blueprint`, `$source`,
`$path`, `$identifier`, `$createdAt`, `$updatedAt`, `$syncedAt`) or a bare
`attributes` key. **`$updatedAt` is the vendor's timestamp; `$syncedAt` is
ours** — they are separate properties because sync touches every node on every
run, so answering "what changed?" with `$syncedAt` would describe our cron
schedule rather than any real activity.

Operators: `=` `!=` `contains` `doesNotContain` `beginsWith` `endsWith` `in`
`notIn` `containsAny` `>` `>=` `<` `<=` `between` `notBetween` `isEmpty`
`isNotEmpty`, plus `relatedTo` / `notRelatedTo` on relations (with `direction`
and `maxHops`, resolved through `graph/traversal.py`'s recursive CTE).
`notRelatedTo` is not a Port operator — it exists because every "what's
missing" question needs it.

`beginsWith` on `$path` compiles to ltree's `<@` containment rather than a
string match, so it uses `ix_node_path_gist` and means "everything underneath".

The response is a **shared node dictionary**, not a list of cards: every node
appears exactly once and is referenced by short id from `anchors` and `edges`.
Hierarchy travels as each node's `path` and is never re-sent as edges (CONTAINS
is ~83% of all edges). `rollup` carries counts across the whole match set, which
is constant-size regardless of how many rows matched. Measured against the
older `/search-cards` on the same query: 4.9 KB vs 85 KB.

## Graph — `api/routes/graph.py`

| Method | Path | Notes |
|---|---|---|
| GET | `/api/graph/nodes/{id}/edges` | `?type=&direction=&max_hops=` — feeds the Cytoscape explorer |
| GET | `/api/graph/traverse` | `{root_id, edge_types, max_hops, direction}` — general traversal, used by both UI and internal debugging |

## Context spaces (logical layer) — `api/routes/context_spaces.py`

| Method | Path | Notes |
|---|---|---|
| GET | `/api/context-spaces` | List, `?business_node_id=` filter |
| GET | `/api/context-spaces/{id}` | Full detail incl. bindings |
| POST | `/api/context-spaces` | Create — required fields per `docs/DOMAIN_MODEL.md` "ContextSpace" |
| PATCH | `/api/context-spaces/{id}` | |
| DELETE | `/api/context-spaces/{id}` | |
| POST | `/api/context-spaces/{id}/bindings` | Add a binding (capability + connector instance + native container) |
| DELETE | `/api/context-spaces/{id}/bindings/{binding_id}` | |
| GET | `/api/edges/proposed` | `SYNC_EXTRACTED` edges with `state=PROPOSED`, for the review queue |
| POST | `/api/edges/{id}/confirm` | Sets `state=ACTIVE`, `origin` stays `SYNC_EXTRACTED` (provenance preserved) |
| POST | `/api/edges/{id}/reject` | Sets `state=REJECTED` |
| PATCH | `/api/edges/{id}` | Retype (e.g. promote `MENTIONS` -> `IMPLEMENTS`); records the human override |

## Reconciliation / retrieval passthroughs

| Method | Path | Notes |
|---|---|---|
| POST | `/api/reconcile` | `{context_space}` — wraps `context-fabric reconcile` |
| POST | `/api/resolve-scope` | Thin wrapper over the MCP `resolve_scope` tool, for UI use without an MCP client |
| POST | `/api/context-pack` | Thin wrapper over `get_context_pack`, same reason |

## Cross-cutting

- **Auth**: every request carries an actor identity; every response is
  filtered through `authorization.filter_visible` exactly as the MCP tools
  are (ADR-007) — the REST API is not a side door around that gate.
- **Errors**: problem-details JSON (`{type, title, status, detail}`), error
  category from the connector layer surfaced as `detail`, never a raw
  vendor error body.
- **Pagination**: cursor-based (`?cursor=`), consistent with
  `SourceConnector.list_children`'s pagination shape, so the same UI
  pagination component works for catalog browsing and native connector
  paging alike.
