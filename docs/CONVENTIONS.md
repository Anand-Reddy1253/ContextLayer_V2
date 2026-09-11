# Conventions

Code-level rules that apply across every phase. `AGENTS.md` is the binding
contract; this file is the reference for "how," not "whether."

## Async

Everything I/O-bound is `async def`: connectors, repositories,
synchronization, API routes, MCP tools. Domain models and pure functions
(ranking math, YAML parsing) stay synchronous — don't wrap something async
that does no I/O.

## Error categories

Every raised error from `connectors/` and `synchronization/` is one of:

```
AuthError       — bad/expired credential, insufficient vendor permission
RateLimited     — vendor rate limit hit; retryable after backoff
NotFound        — object doesn't exist (may mean deleted; sync treats
                   distinctly from a get_changes-reported tombstone)
Transient       — network/timeout/5xx; retryable
Permanent        — 4xx other than auth/not-found/rate-limit; not retryable
SchemaDrift      — vendor payload shape didn't match what mapper.py expects;
                   never silently coerced, always raised and logged
```

Callers branch on category (`except RateLimited:` etc.), never on message
text or status code directly outside the connector that raised it.

## Structured logging

structlog everywhere, key-value fields, not f-string messages:

```python
logger.info("sync.node_upserted", node_id=node.id, source_system=source,
            correlation_id=ctx.correlation_id)
```

Every sync run and every MCP/API request carries one `correlation_id`
through all its log lines (`observability/`). Never log: credentials,
tokens, full retrieved content bodies (a hash or length is fine, the body
is not), or a raw vendor payload (log the mapped domain object's
identifying fields instead).

## Naming

- Python: `snake_case` modules/functions, `PascalCase` classes,
  `SCREAMING_SNAKE_CASE` enum members.
- Vendor-neutral vocabulary in anything user- or agent-facing: capability
  names (`docs/adr/ADR-004-capability-based-naming.md`), not vendor
  product names, in slot names, edge semantics, and API field names.
  Vendor names live in `source_system` values and connector package names
  only.
- Domain types in `domain/` have no `Model`/`Schema`/`DTO` suffix — they
  are just the noun (`Node`, `Edge`, `ContextSpace`). SQLAlchemy ORM
  classes in `persistence/` get an `ORM` prefix or module-qualified import
  (`persistence.models.Node`) to keep the two apart at a glance in code
  review.

## Test layout

```
tests/unit/          pure logic, no I/O, milliseconds, no docker-compose
tests/integration/   real Postgres + fixture connectors, no live network
tests/acceptance/    end-to-end gates named across docs/phases/*.md —
                      idempotency, anti-leakage, authorization exclusion
```

One test file per source module (`tests/unit/domain/test_node.py` for
`domain/node.py`), mirroring package structure. Acceptance tests are named
after the gate they prove (`test_sync_is_idempotent.py`,
`test_connectors_never_leak_vendor_shapes.py`,
`test_unauthorized_evidence_excluded_from_pack.py`) rather than after a
phase number, so they stay meaningful once phases are long finished.

## Migrations

Alembic, one migration per logical schema change, forward-only — see
`migrations/README.md`. `CF_DATABASE_URL` from environment only, never
hardcoded.

## Configuration vs. code

If a change can be expressed as an edit to `configs/*.yaml`
(`stage-contracts.yaml`, `capabilities.yaml`, a `context-spaces/*.yaml`),
it must be — not as a new `if` branch in `retrieval/compiler.py` or
`synchronization/`. This is what "stage contracts are configuration-driven"
means in practice (`docs/RETRIEVAL.md` §2).

## Docker base images

Pinned major versions (`python:3.12-slim`, `postgres:17-alpine`,
`node:22-alpine`) — never `:latest`, so a rebuild six months from now
doesn't silently change behavior.
