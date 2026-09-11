"""Observability.

structlog configuration (JSON in prod, console in dev), correlation-id
context propagation (one ID per sync run and per MCP/API request), and the
logging redaction rule enforced everywhere: never log credentials, tokens,
or raw source content (docs/SECURITY.md).

Depends on nothing else in this package (leaf utility, imported by
everything). Implemented in Phase 14 (docs/phases/PHASE-14.md); a minimal
structlog setup is pulled forward wherever earlier phases need logging.
"""
