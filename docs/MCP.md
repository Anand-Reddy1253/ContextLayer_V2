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

All are read-oriented. None writes to a vendor source (`AGENTS.md` §4/§6) or to
the graph beyond `task_checkpoint` bookkeeping implied by orchestration.

### Built today — the query tools

Implemented in `mcp/tools.py` (transport-agnostic, registered by
`server_stdio.py`; an HTTP transport would register the same functions):

| Tool | Purpose |
|---|---|
| `describe_schema(kind?)` | Queryable kinds, their attribute keys, relation types. **Call first** — `node.kind` is a free string, so the vocabulary only exists as whatever has been synced. |
| `search_entities(query, limit)` | The rule grammar (`domain/query.py`); returns the shared-node-dictionary shape documented in `docs/API.md`. |
| `aggregate_entities(query, group_by)` | Live GROUP BY. One call instead of fetching rows to count them. |
| `search_context(q, ...)` | The original keyword search, kept for compatibility. |
| `resolve_scope(task_ref, actor_id, context_space_override?)` | Which repo/team/product a task belongs to (`retrieval/scope.py`). Deterministic, no model call. See below for the shape. |

`.claude/skills/context-fabric-query/SKILL.md` teaches an agent to use these —
discover schema, build a query, read the response — and states the known gaps
so it says "we don't track that" rather than inventing an answer.

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
// Output (ScopeResolution, retrieval/scope.py)
{
  "task_ref": "AB#312",
  "actor_id": "user-123",
  "resolved": true,
  "reason": null,
  "source_system": "azure_devops",
  "native_id": "312",
  "node_id": "…",
  "context_space_id": "talentflow/identity-squad",
  "product": "talentflow",
  "teams": ["identity-squad"],
  "services": ["identity-service"],
  "repositories": ["acme-org/identity-service"],
  "candidates": []
}
```

Implements `docs/RETRIEVAL.md` §1. `context_space_override`, when set,
skips searching every context space and resolves directly against the named
one. `task_ref` recognizes Azure DevOps (`AB#\d+`), Jira issue keys, GitHub
(`owner/repo#N`), and Confluence (`CONFPAGE-\d+`) — see `retrieval/task_ref.py`.
`candidates` lists every context-space binding that matched, not just the
winner, so ambiguity is visible rather than silently resolved.

This tool never executes anything, and CF has no execution surface at all —
a harness (Claude Code or similar) calls `resolve_scope` to learn which
`repositories` a task belongs to, then `search_entities` for `AI_ASSET`
nodes scoped to those repositories' paths (agent/skill/rule definitions
under `.github/`, `.claude/`, `.cursor/` — see `docs/CONNECTORS.md`'s AI
Explorer section) to learn what's available to run there, then fetches the
full definition via that connector's own on-demand content locator and runs
it itself. CF only ever answers "what's there and where" — it holds no
write path to any vendor and never executes an agent, skill, or workflow on
a caller's behalf.

**Authorization note**: `resolve_scope` does not yet filter `candidates`/
`repositories` by what the caller can see — `authorization/` doesn't exist
yet (see the explicit pass-through seam in `retrieval/scope.py`). Do not
point this at anything multi-tenant until ADR-007 is built, same caveat as
every other tool on this surface today.

### Designed but not built

The two tools below are the original design's remaining pieces. They depend
on an evidence cache with token-budget enforcement and
`configs/stage-contracts.yaml`, neither of which is wired. They are
documented here as intent, not as available surface.

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
