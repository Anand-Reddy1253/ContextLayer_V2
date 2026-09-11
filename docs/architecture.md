# Architecture

Context Fabric builds a context graph over three layers, keeps it in sync
with source systems, and serves it deterministically as search, MCP, and a
UI. This document is the design reference; `docs/phases/` turns it into an
ordered task list, and `AGENTS.md` states the rules that bind both.

## 1. The three layers

```mermaid
flowchart TB
    subgraph BL["Business layer — human-authored (UI)"]
        ORG["ACME"] --> DIV["Engineering"] --> TRIBE["TalentFlow"] --> SQUAD["Identity Squad"]
        SQUAD --> TEAM["Team A"]
    end

    subgraph LL["Logical layer — human-authored (UI)"]
        CS["ContextSpace: talentflow/identity"]
    end

    subgraph TL["Technical layer — connector-sourced, read-only"]
        subgraph ADO["Azure DevOps"]
            ADOP["Project"] --> AP["Area Path"] --> EPIC["Epic"] --> FEAT["Feature"] --> STORY["Story"]
        end
        subgraph GH["GitHub"]
            GHO["Org"] --> REPO["Repository"] --> BR["Branch"] --> DIR["Directory"] --> FILE["File"]
        end
        subgraph CONF["Confluence"]
            WS["Workspace"] --> SPACE["Space"] --> PAGE["Parent Page"] --> CHILD["Child Page"]
        end
    end

    SQUAD -.owns.-> CS
    CS -->|binding: WORK_MANAGEMENT| AP
    CS -->|binding: CODE| REPO
    CS -->|binding: DOCUMENTATION| SPACE
```

| Layer | Owned by | Mutable how | Contains |
|---|---|---|---|
| **Business** | Humans, via UI | CRUD in the UI (`docs/UI.md`) | Org → division → tribe → squad → team, products, services |
| **Technical** | Connectors, via sync | Never hand-edited — sync only | Each source's *native* hierarchy, exactly as that source models it |
| **Logical** | Humans, via UI | CRUD in the UI | `ContextSpace` + `Binding` rows that bind a business node to native technical containers, by capability |

The logical layer is what makes the other two useful together: a business
node alone doesn't know where its code lives, and a technical node alone
doesn't know which team owns it. A `ContextSpace` is the human decision that
connects them.

## 2. One graph, one storage engine (ADR-002)

All three layers live in one `node` table and one `edge` table in
PostgreSQL — see `docs/persistence.md` for the schema. `layer` on `node`
and `origin`/`state` on `edge` distinguish where a row came from and how
much to trust it; there is no separate graph database.

```mermaid
erDiagram
    NODE ||--o{ EDGE : "src_id / dst_id"
    NODE ||--o{ EVIDENCE : "node_id"
    NODE {
        uuid id PK
        enum layer "BUSINESS | TECHNICAL | LOGICAL"
        text kind
        text capability
        text source_system
        text source_instance_id
        text native_id
        uuid parent_id FK
        ltree path
        jsonb acl_ref
        text content_hash
        timestamptz deleted_at
    }
    EDGE {
        uuid src_id FK
        uuid dst_id FK
        enum type "CONTAINS | BELONGS_TO | ... | RELATED_TO"
        enum origin "SYNC_STRUCTURAL | SYNC_EXTRACTED | HUMAN | RULE"
        enum state "ACTIVE | PROPOSED | REJECTED"
        uuid evidence_id FK
    }
    EVIDENCE {
        uuid id PK
        uuid node_id FK
        text source_version
        text uri
        jsonb acl_ref
        timestamptz retrieved_at
    }
    CONTEXT_SPACE ||--o{ BINDING : "context_space_id"
    CONTEXT_SPACE {
        uuid id PK
        text name
        uuid business_node_id FK
    }
    BINDING {
        uuid id PK
        text capability
        text source_system
        text native_container
    }
```

## 3. Request-time data flow

```mermaid
sequenceDiagram
    participant Agent
    participant MCP as Context MCP
    participant Retr as retrieval/
    participant Authz as authorization/
    participant Graph as graph/ + persistence/

    Agent->>MCP: get_context_pack(task_ref, stage, actor_id, token_budget)
    MCP->>Retr: resolve scope + compile pack
    Retr->>Graph: locate technical node for task_ref
    Graph-->>Retr: node + ancestor path (ltree)
    Retr->>Graph: find ContextSpace bindings covering that path
    Graph-->>Retr: context spaces, business nodes
    Retr->>Authz: filter_visible(actor, candidate nodes)
    Authz-->>Retr: authorized nodes only
    Retr->>Retr: rank + fill stage-contract slots within token_budget
    Retr-->>MCP: ContextPack (facts + evidence_ids + expansion_handles)
    MCP-->>Agent: ContextPack
```

Authorization runs **before** ranking (ADR-007) — ranking and compilation
never see a node the actor cannot read.

## 4. Sync data flow

```mermaid
flowchart LR
    A[discover_containers] --> B["list_children (paginated, cursored)"]
    B --> C[map vendor payload to domain model]
    C --> D{content_hash changed?}
    D -- no --> E[skip — idempotent]
    D -- yes --> F["upsert node by (source_system, source_instance_id, native_id)"]
    F --> G[create/update structural CONTAINS edges]
    G --> H[get_links -> extract mentions]
    H --> I{resolves to a known node?}
    I -- yes --> J["create MENTIONS/RELATED_TO edge (origin=SYNC_EXTRACTED, state=PROPOSED)"]
    I -- no --> K[park in unresolved_link]
    B --> L["get_changes(cursor) — deletes"]
    L --> M[tombstone: set deleted_at]
```

Running the same fixture data through this pipeline twice must produce zero
net graph change — the idempotency gate tested in
`docs/phases/PHASE-06.md`.

## 5. Actual lineage vs. structural containment

Two different relationship shapes coexist on the same edge table:

- **Structural containment** (`origin=SYNC_STRUCTURAL`): a source's native
  hierarchy — Project → Area Path → Epic → Story, or Org → Repo → Branch →
  Path → File. Always `CONTAINS`/`BELONGS_TO`.
- **Actual lineage** (`origin=SYNC_EXTRACTED` or `HUMAN`): the real delivery
  chain when links exist in the source data —
  `Requirement -> Design -> Pull Request -> Commit -> Build -> Test Result -> Deployment`,
  via `SPECIFIED_BY`, `IMPLEMENTS`, `CHANGES`, `VERIFIES`, `DEPENDS_ON`.

Lineage edges are only created where evidence exists (a link, a mention, a
human-drawn binding) — never inferred by guessing.

## 6. Components

| Package | Responsibility | Depends on |
|---|---|---|
| `domain/` | Pydantic models, enums, errors. No I/O. | nothing in this repo |
| `persistence/` | SQLAlchemy models, repositories, session/engine | `domain/` |
| `connectors/` | `SourceConnector` implementations (fixture + live) | `domain/` |
| `synchronization/` | Orchestrates connectors → domain → persistence, idempotently | `domain/`, `persistence/`, `connectors/`, `graph/` |
| `catalog/` | Business layer + logical layer (`ContextSpace`/`Binding`) writes | `domain/`, `persistence/` |
| `graph/` | Traversal (recursive CTE, ltree) | `domain/`, `persistence/` |
| `authorization/` | `can_read` / `filter_visible`, applied before ranking | `domain/`, `persistence/` |
| `retrieval/` | Scope resolution, context-pack compiler, stage contracts | `domain/`, `persistence/`, `graph/`, `authorization/`, `catalog/` — never `connectors/` |
| `observability/` | structlog config, correlation IDs, redaction | leaf, depended on by all |
| `api/` | REST routes consumed by `ui/` | `retrieval/`, `catalog/`, `graph/`, `synchronization/`, `authorization/` |
| `mcp/` | The one Context MCP server, stdio + HTTP | `retrieval/`, `catalog/`, `authorization/` |
| `cli/` | `context-fabric` Typer app | `synchronization/`, `connectors/`, `retrieval/` |
| `ui/` | React SPA — business + logical layer authoring, read-only catalog/graph browsing | Context Fabric REST API only |

See `src/context_fabric/__init__.py` for the enforced dependency direction
and the two rules that matter most (retrieval never imports connectors;
connectors never leak vendor shapes).

## 7. Explicitly out of scope

Vector embeddings, semantic search, LLM-generated summaries, a dedicated
graph database, full Confluence/Jira/Notion/ClickUp connectors, full
repository AST parsing, a custom Graphify replacement, source-system
writes, autonomous inference of team ownership, full raw-content
replication, Kubernetes, premature microservices, complex event-bus
infrastructure. See `AGENTS.md` §4 for the authoritative, binding list and
ADR-001 for why.

## 8. Where to go next

- `docs/DOMAIN_MODEL.md` — every entity and field
- `docs/persistence.md` — the actual schema and indexes
- `docs/CONNECTORS.md` — the `SourceConnector` protocol
- `docs/RETRIEVAL.md` — scope resolution and the pack compiler
- `docs/MCP.md` — the four MCP tools
- `docs/API.md` / `docs/UI.md` — the REST surface and the UI that consumes it
- `docs/SECURITY.md` — authorization and secret handling
- `docs/adr/` — the decisions behind each of the above
