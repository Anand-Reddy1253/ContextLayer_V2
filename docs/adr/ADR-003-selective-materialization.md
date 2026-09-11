# ADR-003: Selective materialization

## Status
Accepted

## Context
Two extremes were both rejected: replicate every source's full content into
Postgres ("do not implement: full raw-content replication"), or fetch
everything live on every query (too slow, too fragile to rate limits, no
offline story).

## Decision
Sync persists **metadata only**: identity, hierarchy position, name,
description, owners, status, version, `source_version`/`content_hash`,
ACL reference, and extracted links. It does not persist full document or
file bodies.

Full content is fetched on demand, only for evidence a context pack
actually selected, via the connector's `get_content` — invoked by
`expand_evidence` and `refresh_evidence` (`docs/MCP.md`), never by sync
itself.

`content_hash` on the metadata row is still enough to detect that content
*changed* without storing what it changed to — sync compares hashes to
decide whether a node's `source_version` needs bumping and whether
downstream evidence is stale.

## Consequences
- Storage stays proportional to the number of tracked objects, not their
  total content size.
- A context pack can go stale in ways metadata alone won't catch (body
  edited, hash unchanged if the source doesn't expose one reliably) — this
  is why `max_age_days` and `refresh_evidence` exist as a backstop
  (`docs/RETRIEVAL.md`), not just content-hash comparison.
- `get_content` calls are synchronous with user-facing requests
  (`expand_evidence`), so they inherit the connector's normal timeout/
  retry/rate-limit stack (`docs/CONNECTORS.md`) — there is no separate
  "bulk content fetch" code path to keep in sync.
