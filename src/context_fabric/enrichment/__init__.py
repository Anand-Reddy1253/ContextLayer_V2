"""LLM-generated search metadata — offline, additive, never in the
get_context_pack path (ADR-010, AGENTS.md §4's named exception).

Nothing here runs during sync (ADR-003: sync persists metadata only, and
never calls get_content itself). Every module is triggered on demand —
today, only via `POST /api/connectors/{id}/enrich`
(api/routes/connectors.py) — and writes bounded, regenerable, plain-text
attributes onto existing nodes. It never invents a node and never touches
`get_context_pack`'s deterministic retrieval path.
"""
