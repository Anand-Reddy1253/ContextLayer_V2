# Connectors

The `SourceConnector` protocol, the fixture/live split, and the step-by-step
process for adding a new connector. Implemented starting Phase 3
(`docs/phases/PHASE-03.md`); ADO (Phase 4) is the reference implementation.

## The protocol

```python
class SourceConnector(Protocol):
    source_system: str        # e.g. "azure_devops"
    mode: Literal["fixture", "live"]

    async def discover_containers(self) -> list[SourceContainer]:
        """Top-level containers this connector instance can see —
        e.g. ADO projects, GitHub orgs/repos."""
        ...

    async def list_children(
        self, parent_id: str, cursor: str | None = None,
    ) -> Page[SourceObject]:
        """Paginated children of a container or object, in native hierarchy
        order (see 'Native hierarchies' below)."""
        ...

    async def get_object(self, native_id: str) -> SourceObject:
        ...

    async def get_content(
        self, native_id: str, version: str | None = None,
    ) -> SourceContent:
        """Full body, fetched on demand only (ADR-003) — never called by
        sync itself, only by expand_evidence/refresh_evidence."""
        ...

    async def get_changes(self, cursor: str | None = None) -> ChangePage:
        """Delta feed since cursor, including deletions/tombstones."""
        ...

    async def get_links(self, native_id: str) -> list[SourceLink]:
        """Explicit and mentioned links out of this object, for
        relationship extraction (docs/RETRIEVAL.md is not involved here —
        this is a sync-time concern, see synchronization/)."""
        ...

    async def get_acl_reference(self, native_id: str) -> ACLReference:
        """Opaque pointer, resolved later by authorization/. A connector
        never decides who can read something — it only reports the
        source's own access-control identity for that object."""
        ...
```

Every return type is a `domain/` type (`docs/DOMAIN_MODEL.md`
"Connector-facing types"). No method may return a vendor SDK object or a
raw `dict` shaped like the vendor's JSON — that translation happens inside
the connector's own `mapper.py` and stops there (`AGENTS.md` §5).

## Fixture mode vs. live mode

| | Fixture | Live |
|---|---|---|
| Data source | `fixtures/<source>/*.json` | Real vendor API |
| Credentials | None | `.env` (`CF_MODE=live` + per-connector vars) |
| Network | None | Yes |
| Default | Yes | No — explicitly opted into |
| Used by | CI, acceptance tests, local dev | Phase 19 only, opt-in |

Both modes implement the same Protocol; callers (`synchronization/`,
`cli/`) never branch on mode — the connector object itself already knows
which one it is.

## Cross-cutting requirements (every connector, both modes)

All implemented once in `connectors/base.py`, inherited, not
reimplemented:

- **Async I/O** throughout.
- **Pagination**: `list_children`/`get_changes` always honor `cursor`
  and return an opaque `next_cursor`; never assume a full result set fits
  one page.
- **Timeouts** on every network call (live mode).
- **Retry**: bounded exponential backoff with jitter (tenacity), retried
  only for `Transient`/`RateLimited` categories — never for `Permanent`/
  `NotFound`/`AuthError`.
- **Rate-limit awareness**: read the vendor's rate-limit headers where
  available and back off proactively, not just reactively on 429.
- **Idempotent synchronization**: calling sync twice with no source
  changes produces zero net graph change (the Phase 6 acceptance gate).
- **Correlation IDs**: every call carries the calling sync run's
  correlation ID into structured logs (`observability/`).
- **Structured logging**: structlog, key-value fields, no string
  interpolation of secrets or raw content.
- **Explicit error categories**: every raised error is one of
  `AuthError`, `RateLimited`, `NotFound`, `Transient`, `Permanent`,
  `SchemaDrift` — callers branch on category, never on message text.
- **Tombstone/deletion handling**: `get_changes` reports deletions
  explicitly (`SourceObject.deleted=True`), and sync sets `deleted_at`
  rather than hard-deleting a `node` row.
- **No credentials committed to the repository** — ever. See
  `.env.example` and `docs/SECURITY.md`.

## Native hierarchies (what `list_children` walks)

| Source | Hierarchy |
|---|---|
| Azure DevOps | Project → Area Path → Epic → Feature → Story/Task/Bug |
| GitHub | Organization → Repository → Branch → Directory → File |
| Confluence *(future, not implemented — full connector explicitly out of scope, `AGENTS.md` §4)* | Workspace → Space → Parent Page → Child Page |

Each container and object gets a unique `native_id` and, where the source
provides one, a description — both preserved in the mapped `Node`
(`attributes`/`description` fields, `docs/DOMAIN_MODEL.md`).

## Anti-leakage test

`tests/acceptance/` includes a test that walks every public method on every
registered connector and asserts the return type is a `domain/` model, not
a `dict`/vendor SDK type. This test is part of the Phase 3 exit gate and
must stay green permanently — it is the enforcement mechanism for
`AGENTS.md` §5's "no vendor payload leakage" rule.

## Adding a new connector — checklist

1. `connectors/<source>/__init__.py` with the same docstring pattern as
   `connectors/azure_devops/__init__.py`.
2. `connectors/<source>/mapper.py` — vendor payload → `domain/` types.
   This is the *only* file allowed to know the vendor's JSON shape.
3. `connectors/<source>/fixture.py` — implements `SourceConnector` reading
   `fixtures/<source>/*.json`.
4. `connectors/<source>/live.py` *(only when actually enabling live mode,
   Phase 19)* — implements `SourceConnector` over the real API, using
   `connectors/base.py`'s retry/backoff/timeout stack.
5. `fixtures/<source>/` — deterministic JSON, including at least one
   deletion and one pagination boundary (see `fixtures/azure_devops/README.md`
   for the pattern).
6. Register the connector in `synchronization/registry.py` (added in
   Phase 6) and add its `Capability` mappings to
   `configs/capabilities.yaml`'s `served_by` lists (documentation only).
7. Add it to the anti-leakage test's connector list.
8. `context-fabric sync --source <source> --fixture` runs clean, twice, with
   zero net graph change on the second run.
