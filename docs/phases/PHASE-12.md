# Phase 12 — Context MCP (stdio + HTTP)

## Goal
Expose `resolve_scope`, `get_context_pack`, `expand_evidence`,
`refresh_evidence` exactly as specified in `docs/MCP.md`, over both
transports, from one tool implementation.

## Inputs
- `docs/MCP.md` — exact I/O schemas, must match verbatim.
- `retrieval/scope.py`, `retrieval/compiler.py` (Phases 9-10, now
  authorization-filtered per Phase 11).

## Files to create
- `mcp/tools.py` — the four tool functions, transport-agnostic. Each
  resolves `actor_id` the same way regardless of caller (`docs/MCP.md`
  "Both transports resolve to the same actor_id -> authorization/ flow").
- `mcp/pack_cache.py` — short-lived in-process (or Redis-free, DB-backed if
  simpler) cache keyed by `context_pack_id`, used only by
  `expand_evidence`/`refresh_evidence` to avoid re-sending the whole pack
  — explicitly not `task_checkpoint` (ADR-008: packs are caches, not
  sources of truth; this cache can be evicted/restarted with no data-loss
  implications beyond needing a fresh `get_context_pack` call).
- `mcp/server_stdio.py` — stdio transport entrypoint, `actor_id` from
  `CF_ACTOR_ID` env var.
- `mcp/server_http.py` — streamable-HTTP transport, mountable on the
  FastAPI app (`main.py` wiring happens in Phase 15, but this module
  should be self-contained and testable standalone in this phase).

## Acceptance criteria
- `resolve_scope`/`get_context_pack` input/output JSON shapes match
  `docs/MCP.md` exactly — verify with a schema/contract test comparing
  actual tool output against the documented example shape's keys.
- `expand_evidence` only fetches content for the requested `evidence_ids`,
  re-checks authorization for each (an evidence item unauthorized in the
  original pack must also be refused here, not just omitted from the
  pack), and does not re-run scope resolution.
- `refresh_evidence` compares `source_version` before re-fetching content —
  a test with an unchanged `source_version` proves no connector call
  happens; a changed one proves it does.
- Both transports produce identical results for the same
  (task_ref, actor_id, stage) input — a parametrized test running the same
  case through both.

## Tests to write
`tests/integration/mcp/test_tools.py` (transport-agnostic core logic),
`tests/integration/mcp/test_stdio_transport.py`,
`tests/integration/mcp/test_http_transport.py`.

## Exit gate
`pytest tests/integration/mcp -q` green. Manually invoke the stdio server
once (documented command in the report) to confirm it actually speaks MCP,
not just that the Python-level tool functions work.
