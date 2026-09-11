# Security

Authorization model, secret handling, and the untrusted-content stance.
Implemented in Phase 11 (`docs/phases/PHASE-11.md`); the rules below apply
from Phase 1 onward regardless of which phase "owns" the enforcement code —
no phase gets a pass on logging a secret because authorization isn't built
yet.

## Authorization abstraction

```python
class AuthorizationService(Protocol):
    async def can_read(self, actor: Actor, acl_ref: dict) -> bool: ...
    async def filter_visible(self, actor: Actor, nodes: list[Node]) -> list[Node]: ...
```

Rules (ADR-007):

- **Applied before ranking and context compilation** — `retrieval/` and
  `api/` call `filter_visible` at the repository query layer, never as a
  post-filter on already-ranked or already-compiled output.
- **Context-space membership grants no source access.** Being listed as a
  `ContextSpace` owner/team does not imply read access to any node — access
  is always resolved from the node's/evidence's own `acl_ref`.
- **Derived fragments inherit the restrictions of their source.** A
  context-pack slot item built from a node with `acl_ref=X` is exactly as
  restricted as `X`; compilation never widens access.
- **Deletions and access revocation are supported.** A tombstoned node
  (`deleted_at` set) or a revoked `acl_ref` must stop appearing in
  `filter_visible` results on the next check — no caching of a stale grant
  beyond what `docs/RETRIEVAL.md` §5 freshness rules already bound.

## Fixture-mode authorization

`fixtures/authz/actors.yaml` (actor → groups) and
`fixtures/authz/acl_grants.yaml` (acl_ref → permitted groups) back a
simplified `AuthorizationService` implementation for fixture mode. This is
still the real code path — not a bypass — so every test exercises the same
logic that runs in a real deployment with a real identity/ACL resolver
swapped in later.

**Fixture tests must prove a negative**: at least one authorization
acceptance test asserts that a specific piece of evidence, reachable in the
graph and relevant to a stage contract, is *excluded* from
`get_context_pack`'s output for an actor who lacks the grant for it
(`docs/phases/PHASE-11.md`). A test suite with only positive-access tests
does not satisfy this requirement.

## Secrets

- **Never committed**: `.env` is git-ignored (`.gitignore`); `.env.example`
  documents every variable name with no real values.
- **Encrypted at rest**: `connector_connection.credential_ciphertext`
  (`docs/persistence.md`) uses Fernet symmetric encryption keyed by
  `CF_SECRET_KEY` (env-only, never in the database, never in a migration).
- **Never logged**: `observability/`'s structlog processors redact any
  field named `credential`, `token`, `password`, `secret`, or `authorization`
  before a log line is emitted, in addition to callers simply never passing
  them to a logger.
- **Never returned by a read API**: `GET /api/connectors` and friends never
  include `credential_ciphertext` or a decrypted value in any response —
  write-only from the API's perspective (`docs/API.md`, `docs/UI.md`).

## Untrusted content

Every piece of source text Context Fabric retrieves (a Confluence page
body, a work-item description, a PR title) is **data, not instructions**.
This applies at every layer:

- `connectors/` never executes or interprets retrieved text as commands.
- `mcp/` tool outputs are documented (`docs/MCP.md`) as untrusted content
  for the calling agent to treat accordingly — Context Fabric's own
  responsibility is to never itself act on retrieved text as if it were a
  directive (e.g. sync never "follows an instruction" found in a work-item
  body).
- Provenance (`evidence_id`, source, `acl_ref`) travels with content
  through every transformation — ranking, truncation, expansion — so a
  consumer can always tell where a fact came from and what access
  constraints it inherited.

## Read/write separation

`connectors/` implements **read operations only** — `discover_containers`,
`list_children`, `get_object`, `get_content`, `get_changes`, `get_links`,
`get_acl_reference`. There is no write method on the `SourceConnector`
protocol, by design (`AGENTS.md` §4/§6, ADR-001). If a future requirement
needs Context Fabric to write back to a vendor system, that is a new
protocol and a new ADR — it does not get bolted onto `SourceConnector`.

## Threat model notes (fixture-mode PoC scope)

This PoC does not implement a real identity provider, network-level
access control, or secrets-manager integration — those are deployment
concerns layered on top in a real rollout. What it does guarantee, and
what its acceptance tests enforce, is that the *authorization decision
point* is correctly placed (before ranking, never bypassable via a
different code path) and that the *secret-handling discipline* (never
committed, never logged, never returned) holds even in a simplified
fixture-mode setup.
