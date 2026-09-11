# Persistence — PostgreSQL schema

Implemented in Phase 2 (`docs/phases/PHASE-02.md`). Every table here mirrors
an entity in `docs/DOMAIN_MODEL.md` field-for-field — if they diverge,
`DOMAIN_MODEL.md` is wrong or this file is; fix whichever is stale, don't
let them drift apart.

Extensions required: `pgcrypto` (UUID generation), `ltree` (path
containment queries).

## Tables

### `node`

```sql
CREATE TABLE node (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    layer               TEXT NOT NULL CHECK (layer IN ('BUSINESS','TECHNICAL','LOGICAL')),
    kind                TEXT NOT NULL,
    capability          TEXT NULL,
    name                TEXT NOT NULL,
    description         TEXT NULL,
    owners              JSONB NOT NULL DEFAULT '[]',
    source_system       TEXT NULL,
    source_instance_id  TEXT NULL,
    native_id           TEXT NULL,
    parent_id           UUID NULL REFERENCES node(id),
    path                LTREE NOT NULL,
    status              TEXT NOT NULL DEFAULT 'ACTIVE',
    version             INT NOT NULL DEFAULT 1,
    source_version      TEXT NULL,
    content_hash        TEXT NULL,
    acl_ref             JSONB NOT NULL DEFAULT '{}',
    attributes          JSONB NOT NULL DEFAULT '{}',
    first_seen_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at          TIMESTAMPTZ NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX ux_node_technical_identity
    ON node (source_system, source_instance_id, native_id)
    WHERE layer = 'TECHNICAL';

CREATE INDEX ix_node_path_gist ON node USING GIST (path);
CREATE INDEX ix_node_parent ON node (parent_id);
CREATE INDEX ix_node_layer_kind ON node (layer, kind);
CREATE INDEX ix_node_capability ON node (capability) WHERE capability IS NOT NULL;
CREATE INDEX ix_node_not_deleted ON node (id) WHERE deleted_at IS NULL;
```

`path` is maintained by `persistence/` on insert/reparent (never by a
trigger doing implicit business logic) — see `graph/traversal.py` for the
ltree query patterns it enables (`path <@ 'acme.eng.talentflow.identity'`
style ancestor/descendant lookups).

### `edge`

```sql
CREATE TABLE edge (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    src_id        UUID NOT NULL REFERENCES node(id),
    dst_id        UUID NOT NULL REFERENCES node(id),
    type          TEXT NOT NULL CHECK (type IN (
                      'CONTAINS','BELONGS_TO','OWNED_BY','HAS_SERVICE',
                      'IMPLEMENTED_BY','SPECIFIED_BY','IMPLEMENTS','CHANGES',
                      'VERIFIES','DEPENDS_ON','MENTIONS','RELATED_TO')),
    origin        TEXT NOT NULL CHECK (origin IN
                      ('SYNC_STRUCTURAL','SYNC_EXTRACTED','HUMAN','RULE')),
    confidence    REAL NOT NULL DEFAULT 1.0,
    state         TEXT NOT NULL DEFAULT 'ACTIVE'
                      CHECK (state IN ('ACTIVE','PROPOSED','REJECTED')),
    evidence_id   UUID NULL REFERENCES evidence(id),
    attributes    JSONB NOT NULL DEFAULT '{}',
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at    TIMESTAMPTZ NULL
);

CREATE UNIQUE INDEX ux_edge_identity ON edge (src_id, dst_id, type, origin);
CREATE INDEX ix_edge_src ON edge (src_id, type) WHERE deleted_at IS NULL;
CREATE INDEX ix_edge_dst ON edge (dst_id, type) WHERE deleted_at IS NULL;
CREATE INDEX ix_edge_state ON edge (state) WHERE state = 'PROPOSED';
```

### `evidence`

```sql
CREATE TABLE evidence (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    node_id             UUID NOT NULL REFERENCES node(id),
    source_system       TEXT NOT NULL,
    source_instance_id  TEXT NOT NULL,
    native_id           TEXT NOT NULL,
    source_version      TEXT NULL,
    uri                 TEXT NOT NULL,
    content_hash        TEXT NULL,
    acl_ref             JSONB NOT NULL DEFAULT '{}',
    retrieved_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_evidence_node ON evidence (node_id);
```

### `context_space`

```sql
CREATE TABLE context_space (
    id                 TEXT PRIMARY KEY,           -- e.g. 'talentflow/identity'
    business_node_id   UUID NOT NULL REFERENCES node(id),
    name               TEXT NOT NULL,
    description        TEXT NOT NULL DEFAULT '',
    owners             JSONB NOT NULL DEFAULT '[]',
    product            TEXT NULL,
    teams              JSONB NOT NULL DEFAULT '[]',
    services           JSONB NOT NULL DEFAULT '[]',
    status             TEXT NOT NULL DEFAULT 'active',
    version            INT NOT NULL DEFAULT 1,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### `binding`

```sql
CREATE TABLE binding (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    context_space_id    TEXT NOT NULL REFERENCES context_space(id) ON DELETE CASCADE,
    capability          TEXT NOT NULL,
    source_system       TEXT NOT NULL,
    source_instance_id  TEXT NOT NULL,
    native_container    TEXT NOT NULL,
    origin              TEXT NOT NULL DEFAULT 'HUMAN',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_binding_context_space ON binding (context_space_id);
CREATE INDEX ix_binding_lookup ON binding (source_system, source_instance_id, native_container);
```

### `sync_state`

```sql
CREATE TABLE sync_state (
    source_system         TEXT NOT NULL,
    scope_id               TEXT NOT NULL,
    cursor                  TEXT NULL,
    last_event_id           TEXT NULL,
    last_successful_sync    TIMESTAMPTZ NULL,
    last_reconciliation     TIMESTAMPTZ NULL,
    status                   TEXT NOT NULL DEFAULT 'PENDING',
    error                    TEXT NULL,
    PRIMARY KEY (source_system, scope_id)
);
```

### `sync_run`

```sql
CREATE TABLE sync_run (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_system     TEXT NOT NULL,
    scope_id          TEXT NOT NULL,
    correlation_id    TEXT NOT NULL,
    started_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at       TIMESTAMPTZ NULL,
    status            TEXT NOT NULL DEFAULT 'RUNNING',
    nodes_upserted    INT NOT NULL DEFAULT 0,
    nodes_tombstoned  INT NOT NULL DEFAULT 0,
    edges_created     INT NOT NULL DEFAULT 0,
    error_category    TEXT NULL,
    error_detail      TEXT NULL
);

CREATE INDEX ix_sync_run_scope ON sync_run (source_system, scope_id, started_at DESC);
```

### `task_checkpoint`

```sql
CREATE TABLE task_checkpoint (
    task_ref              TEXT PRIMARY KEY,
    stage                 TEXT NOT NULL,
    objective             TEXT NOT NULL DEFAULT '',
    context_space_ids     JSONB NOT NULL DEFAULT '[]',
    accepted_decisions    JSONB NOT NULL DEFAULT '[]',
    completed_actions     JSONB NOT NULL DEFAULT '[]',
    files_changed         JSONB NOT NULL DEFAULT '[]',
    tests_executed        JSONB NOT NULL DEFAULT '[]',
    unresolved_questions  JSONB NOT NULL DEFAULT '[]',
    evidence_versions     JSONB NOT NULL DEFAULT '{}',
    repository_sha        TEXT NULL,
    updated_at             TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### `connector_connection`

Not in the original entity list, required to back "one page which takes the
connector details and saves in db" (UI requirement, `docs/UI.md`
"Connectors screen").

```sql
CREATE TABLE connector_connection (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_system       TEXT NOT NULL,           -- 'azure_devops' | 'github'
    instance_id         TEXT NOT NULL,           -- unique per source_system
    display_name        TEXT NOT NULL,
    mode                TEXT NOT NULL DEFAULT 'fixture',  -- 'fixture' | 'live'
    config              JSONB NOT NULL DEFAULT '{}',       -- non-secret config only
    credential_ciphertext BYTEA NULL,             -- Fernet-encrypted, CF_SECRET_KEY (docs/SECURITY.md)
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX ux_connector_connection_identity
    ON connector_connection (source_system, instance_id);
```

`credential_ciphertext` is never returned by any read endpoint or logged —
see `docs/SECURITY.md`.

## Migration discipline

Alembic, one migration per logical change, forward-only (ADR referenced in
`migrations/README.md`: a mistake gets a corrective migration, not an
edited history). `CF_DATABASE_URL` is read from the environment; no
connection string is ever hardcoded in a migration file.

## Query patterns this schema is built for

- **"Everything under this scope"** — `WHERE path <@ :ancestor_path`
  (GiST-indexed), the core of scope resolution (`docs/RETRIEVAL.md`).
- **"What does this node depend on, within N hops"** — bounded recursive
  CTE over `edge`, filtered by `type IN (...)` and `state = 'ACTIVE'`
  (`graph/traversal.py`).
- **"Is this evidence visible to this actor"** — a lookup by `acl_ref`
  against `authorization/`'s resolved grant set, applied before either of
  the above patterns' results are ranked (ADR-007).
