# Context Fabric

A context graph over org structure, connector-sourced technical assets, and
human-authored logical bindings between the two — served as a REST API, a
Context MCP server, and a UI.

**The problem it solves:** in a 50+ team org, knowledge lives in GitHub,
Azure DevOps, Confluence, Jira, and more — split differently per team, with
no shared map of what lives where or how it relates. An agent (or a person)
starting on a work item has no reliable way to find its boundary: which
repo, which docs, which standards apply. Context Fabric builds that map
once, keeps it in sync, and serves it deterministically.

Read `docs/architecture.md` for the full design. Read `AGENTS.md` first if
you are implementing this project — it is the operating contract for the
build.

## Status

Phase 0 (scaffold + docs) is complete. No behavior is implemented yet —
see `docs/PROGRESS.md` for the live phase-by-phase tracker and
`docs/phases/` for what's next.

## Layout

```
configs/        stage contracts, capability vocabulary, context-space examples
src/context_fabric/   domain, persistence, connectors, sync, graph, retrieval,
                       authorization, api, mcp, cli — see docs/architecture.md
migrations/     Alembic
fixtures/       deterministic connector + authz test data
tests/          unit / integration / acceptance
ui/             React + TypeScript + Vite
docs/           architecture, ADRs, per-phase specs, progress tracker
```

## Quickstart (once phases land — not yet functional)

```bash
cp .env.example .env
pip install -e ".[dev]"
docker compose up -d postgres
make migrate

context-fabric sync --source ado --fixture
context-fabric sync --source github --fixture
context-fabric reconcile --context-space talentflow/identity

uvicorn context_fabric.main:app --reload   # REST API + Context MCP (HTTP)
```

UI (via Docker, since Node is not required on the host):

```bash
docker compose up -d ui
# -> http://localhost:5173
```

## Testing

```bash
make test              # everything
make test-unit         # no I/O
make test-integration  # requires: docker compose up -d postgres
make test-acceptance   # idempotency, anti-leakage, authorization gates
```

## Design docs

- [docs/architecture.md](docs/architecture.md) — three-layer design, data flow
- [docs/DOMAIN_MODEL.md](docs/DOMAIN_MODEL.md) — every entity and field
- [docs/persistence.md](docs/persistence.md) — Postgres schema
- [docs/CONNECTORS.md](docs/CONNECTORS.md) — SourceConnector protocol, how to add one
- [docs/RETRIEVAL.md](docs/RETRIEVAL.md) — scope resolution, ranking, stage contracts
- [docs/MCP.md](docs/MCP.md) — the four Context MCP tools
- [docs/API.md](docs/API.md) — REST surface for the UI
- [docs/UI.md](docs/UI.md) — screens and component map
- [docs/SECURITY.md](docs/SECURITY.md) — authorization model, secret handling
- [docs/CONVENTIONS.md](docs/CONVENTIONS.md) — code conventions
- [docs/adr/](docs/adr/) — architecture decision records
