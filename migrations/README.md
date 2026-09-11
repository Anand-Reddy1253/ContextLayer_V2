# Migrations

Alembic migration environment, initialized in Phase 2
([docs/phases/PHASE-02.md](../docs/phases/PHASE-02.md)) alongside the
Postgres schema described in [docs/persistence.md](../docs/persistence.md).

Expected layout once initialized:

```
migrations/
├── env.py          # async engine wiring, reads CF_DATABASE_URL
├── script.py.mako
└── versions/
    ├── 0001_extensions_and_enums.py     # pgcrypto, ltree; layer/kind/edge-type enums
    ├── 0002_node_and_edge.py            # node, edge tables + indexes
    ├── 0003_evidence.py
    ├── 0004_catalog.py                  # context_space, binding
    ├── 0005_sync_state.py               # sync_state, sync_run
    ├── 0006_task_checkpoint.py
    └── 0007_connector_connection.py     # encrypted-at-rest connector config
```

`alembic.ini` will live at the repo root and read `CF_DATABASE_URL` from the
environment — never a hardcoded connection string. Run migrations with
`make migrate` (see [../Makefile](../Makefile)).

Rule (docs/CONVENTIONS.md "Migrations"): every migration is forward-only in
version control; a mistake gets a new corrective migration, not an edited
history.
