# Phase 14 — Observability

## Goal
Formalize the structlog setup, correlation-id propagation, and redaction
rules that earlier phases already depended on informally
(`docs/CONVENTIONS.md` "Structured logging", `docs/SECURITY.md` "Secrets").

## Inputs
- Every earlier phase's ad hoc `logger.info(...)` calls — this phase
  consolidates them onto a single configured logger, it does not
  introduce logging from scratch.

## Files to create
- `observability/logging.py` — structlog configuration: JSON renderer in
  prod (`CF_LOG_FORMAT=json`), console renderer in dev, a processor chain
  including a **redaction processor** that strips/masks any field named
  `credential`, `token`, `password`, `secret`, `authorization` (case
  -insensitive) before the log line is emitted.
- `observability/correlation.py` — a context-local correlation ID
  (contextvars-based), a middleware for `api/` requests, an MCP-call
  wrapper for `mcp/tools.py`, and the existing `@correlate` used by
  `connectors/base.py` (Phase 3) — this phase should confirm/align that
  earlier decorator with the final contextvars implementation rather than
  keeping two separate mechanisms.
- `observability/health.py` — a basic `/healthz` check (DB reachable) for
  `api/`, used by `docker-compose.yml`'s eventual `api` healthcheck.

## Acceptance criteria
- A log line anywhere in the request path (API call, MCP tool call, sync
  run) carries the same `correlation_id` from entry to exit — verified by
  capturing structlog output for one full `get_context_pack` call and
  asserting a single correlation_id value across every line.
- A test that deliberately logs a dict containing a `credential` key
  proves the redaction processor masks it — this is the enforcement test
  for `docs/SECURITY.md` "never logged."
- No earlier phase's connector/sync/retrieval code needs to change its
  call sites (`logger.info("sync.node_upserted", ...)`) — only the logger
  configuration underneath changes. If a call site *does* need to change,
  note why in the report.

## Tests to write
`tests/unit/observability/test_logging.py` (redaction),
`tests/integration/observability/test_correlation.py` (end-to-end
correlation ID propagation through a real MCP call).

## Exit gate
`pytest tests/unit/observability tests/integration/observability -q`
green.
