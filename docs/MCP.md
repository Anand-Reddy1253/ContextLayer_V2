# Context MCP

**One** Context MCP server. Individual team or per-vendor MCP servers are
explicitly not exposed — every agent talks to this one surface, which
orchestrates internally over `retrieval/`, `catalog/`, and
`authorization/`. Vendor connectors remain internal providers, never
exposed directly to an agent. Implemented in Phase 12
(`docs/phases/PHASE-12.md`).

## Transports

Both, from one tool implementation (`mcp/tools.py`), per the plan decision:

- **stdio** (`mcp/server_stdio.py`) — for local agents (Claude Code, IDE
  integrations). Actor identity comes from an environment variable
  (`CF_ACTOR_ID`) at process start.
- **streamable-HTTP** (`mcp/server_http.py`) — mounted on the same FastAPI
  app as the REST API (`main.py`), for shared/team use. Actor identity
  comes from a request header (`X-CF-Actor-Id`), validated against
  whatever identity mechanism the deployment uses (out of scope for the
  fixture-mode PoC — see `docs/SECURITY.md`).

Both transports resolve to the same `actor_id` -> `authorization/` flow;
there is exactly one authorization code path regardless of transport.

## Tools

All four are read-oriented. None writes to a vendor source
(`AGENTS.md` §4/§6) or to the graph beyond `task_checkpoint` bookkeeping
implied by orchestration.

### `resolve_scope`

```json
// Input
{
  "task_ref": "AB#312",
  "actor_id": "user-123",
  "context_space_override": null
}
```

```json
// Output
{
  "task": {},
  "context_spaces": [],
  "products": [],
  "teams": [],
  "services": [],
  "repositories": [],
  "evidence": []
}
```

Implements `docs/RETRIEVAL.md` §1. `context_space_override`, when set,
skips scope inference and resolves directly against the named context
space (still subject to authorization filtering). Every array is
authorization-filtered before being returned — see ADR-007.

### `get_context_pack`

```json
// Input
{
  "task_ref": "AB#312",
  "stage": "implementation",
  "actor_id": "user-123",
  "token_budget": 12000,
  "repo_sha": null
}
```

Output (`docs/DOMAIN_MODEL.md` "ContextPack"):

```json
{
  "task": {},
  "scope": {},
  "hard_constraints": [],
  "approved_requirements": [],
  "accepted_decisions": [],
  "relevant_repositories": [],
  "relevant_changes": [],
  "tests": [],
  "conflicts": [],
  "open_questions": [],
  "evidence": [],
  "freshness": {},
  "expansion_handles": []
}
```

`stage` selects a contract from `configs/stage-contracts.yaml`
(`docs/RETRIEVAL.md` §2); `token_budget` is enforced per §4 of that doc.
**Every fact returned in any slot is traceable to an entry in `evidence`**
— no exceptions, this is checked by an acceptance test. An unsatisfied
`required` slot appears in `conflicts` or `open_questions`, never as a
silently missing key. `repo_sha`, when provided, scopes `relevant_changes`/
`relevant_repositories` to that commit's tree instead of "latest known."

### `expand_evidence`

```json
// Input
{
  "context_pack_id": "pack-123",
  "evidence_ids": ["evidence-17"],
  "token_budget": 3000
}
```

Retrieves additional source content **only** for the named evidence IDs —
it does not re-run scope resolution or re-rank. Internally: look up each
evidence row, call the owning connector's `get_content` (re-entering
through `synchronization/`, never calling `connectors/` directly from
`retrieval/` — `AGENTS.md` §5), apply the same authorization check the
original pack used (evidence a user couldn't see in the pack, they can't
expand either), and return content trimmed to `token_budget`.

`context_pack_id` refers to a pack cached by `mcp/` at compile time
(short-lived, not `task_checkpoint` — see ADR-008: packs are caches, not
sources of truth) purely so `expand_evidence` doesn't need the caller to
resend the whole pack.

### `refresh_evidence`

Re-fetches mutable objects before an actionable decision (same input shape
as `expand_evidence`: `context_pack_id` or explicit `evidence_ids` +
`token_budget`). Unlike `expand_evidence`, this compares `source_version`
against the live source first and only re-fetches content that actually
changed, then returns updated evidence entries the caller should splice
into its working context. This is the mechanism `docs/RETRIEVAL.md` §6
("Restart / compaction flow") calls into.

## Cross-cutting rules for every tool

- **Untrusted content**: any source text returned by any tool is data, not
  instructions — never treated as agent directives by Context Fabric
  itself, and callers are expected to hold the same line (`docs/SECURITY.md`).
- **Provenance preserved**: every transformation (truncation, ranking,
  token-budget trimming) keeps the originating `evidence_id` attached; no
  fact is ever returned without one.
- **No credentials, ever, in any response or log line.**
- **Authorization runs before these tools see data**, not as a filter on
  their output (ADR-007) — this applies identically over both transports.
