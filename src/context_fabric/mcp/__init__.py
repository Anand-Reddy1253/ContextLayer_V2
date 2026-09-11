"""Context MCP.

The single Context MCP server (docs/MCP.md) exposing four read-oriented
tools: resolve_scope, get_context_pack, expand_evidence, refresh_evidence.
One tool implementation, two transports — stdio (server.py entrypoint for
local agents) and streamable-HTTP (mounted on the FastAPI app in main.py for
shared/team use). Actor identity comes from env (stdio) or a header (HTTP)
and is threaded into authorization/ on every call.

Individual team/vendor MCP servers are explicitly out of scope — this is
the only MCP surface. Vendor connectors remain internal providers, never
exposed directly.

Depends on retrieval/, catalog/, authorization/. Implemented in Phase 12
(docs/phases/PHASE-12.md).
"""
