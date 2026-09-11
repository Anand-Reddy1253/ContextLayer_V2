# ADR-001: Context Fabric boundary

## Status
Accepted

## Context
Context Fabric sits between vendor systems (GitHub, Azure DevOps,
Confluence, Jira, ...) and consuming agents. Without a clear boundary it is
tempting to let it become either (a) a mirror of every source's full
content, or (b) a place that writes back to those sources, or (c) a UI
framework for general knowledge management. Any of those turns a
metadata-and-relationships problem into a much larger one.

The original build brief also listed "User interface" under "Do not
implement." Working through the design with the requester surfaced that the
UI is not incidental — it is the only place a human declares the business
hierarchy and draws the business-to-technical bindings that make the
logical layer real. Without it, the logical layer has no author.

## Decision
Context Fabric is:

- **Read-only toward every vendor source, forever.** No connector method
  ever writes to ADO, GitHub, Confluence, or Jira. `docs/CONNECTORS.md`
  and `AGENTS.md` §4/§6 make this a hard prohibition, not a phase-1
  simplification.
- **Metadata- and relationship-first, not a content mirror.** See
  ADR-003 (selective materialization). Full text is fetched on demand,
  not replicated wholesale.
- **A first-class UI, deliberately, as the authoring surface for the
  business and logical layers** — this is a recorded deviation from the
  original "no UI" instruction, made explicitly with the requester
  (see ADR-009). Every *other* exclusion from the original scope list
  stands unchanged: no vector search, no embeddings, no LLM summarization,
  no graph database, no full connector implementations beyond ADO/GitHub,
  no Kubernetes, no microservices, no event bus. `AGENTS.md` §4 is the
  authoritative list.
- **Served through one Context MCP surface**, not per-team or per-vendor
  MCP servers (ADR boundary reinforced in docs/MCP.md).

## Consequences
- Every new capability request gets checked against this boundary before
  it is added to a phase spec. "Would this make Context Fabric write to a
  source, mirror full content, or duplicate a vendor's own UI for its own
  data?" — if yes, it does not belong here.
- The UI's scope is itself bounded (ADR-009): it authors business +
  logical layers only. Technical-layer assets stay strictly read-only,
  sync-owned.
