# Domain Model

Every entity Context Fabric persists or exchanges, as it will be modeled in
`src/context_fabric/domain/` (Pydantic v2) and `src/context_fabric/persistence/`
(SQLAlchemy — see `docs/persistence.md` for the table-level schema). This
file is the field-level source of truth; `persistence.md` must not diverge
from it.

## Enums

```
Layer            = BUSINESS | TECHNICAL | LOGICAL
NodeStatus       = ACTIVE | DEPRECATED | ARCHIVED
EdgeType         = CONTAINS | BELONGS_TO | OWNED_BY | HAS_SERVICE
                  | IMPLEMENTED_BY | SPECIFIED_BY | IMPLEMENTS
                  | CHANGES | VERIFIES | DEPENDS_ON | MENTIONS | RELATED_TO
                  | IN_SPACE | AUTHORED_BY | COMMENTED_ON | LINKS_TO
                  | TRANSCLUDES | HAS_LABEL
                  | SUPERSEDES | SUPERSEDED_BY | CAUSED_BY | DECIDES_ON
EdgeOrigin       = SYNC_STRUCTURAL | SYNC_EXTRACTED | HUMAN | RULE | LLM_INFERRED
EdgeState        = ACTIVE | PROPOSED | REJECTED
SyncStatus       = PENDING | RUNNING | SUCCEEDED | FAILED
ErrorCategory    = AUTH | RATE_LIMITED | NOT_FOUND | TRANSIENT | PERMANENT | SCHEMA_DRIFT
Capability       = CODE | DOCUMENTATION | WORK_MANAGEMENT | CHANGE_REVIEW
                  | BUILD_RELEASE | QUALITY | POLICY   (configs/capabilities.yaml)
```

## Node

The single table backing all three layers (ADR-002). Layer-specific rules
(e.g. a TECHNICAL node must carry `source_system`/`native_id`; a BUSINESS
node must not) are validated in the Pydantic model, not by separate tables.

| Field | Type | Notes |
|---|---|---|
| `id` | UUID | PK |
| `layer` | Layer | BUSINESS \| TECHNICAL \| LOGICAL |
| `kind` | str | `ORG`, `DIVISION`, `TRIBE`, `SQUAD`, `TEAM`, `PRODUCT`, `SERVICE` (business); `PROJECT`, `AREA_PATH`, `EPIC`, `FEATURE`, `STORY`, `BUG`, `WORK_ITEM`, `REPOSITORY`, `DIRECTORY`, `FILE`, `PULL_REQUEST`, `COMMIT`, `BUILD`, `DEPLOYMENT`, `TEST_PLAN`, `TEST_RESULT`, `WORKSPACE`, `SPACE`, `PAGE`, `DOCUMENT`, `POLICY_DOCUMENT` (technical); `CONTEXT_SPACE` (logical) |
| `capability` | Capability \| null | set on technical nodes that serve a capability |
| `name` | str | |
| `description` | str \| null | |
| `owners` | list[str] | actor/group identifiers |
| `source_system` | str \| null | e.g. `azure_devops`, `github` — null for BUSINESS/LOGICAL |
| `source_instance_id` | str \| null | which connector instance/connection (a company may have two ADO orgs) |
| `native_id` | str \| null | the vendor's own ID for this object |
| `parent_id` | UUID \| null | FK to `node.id`, structural parent |
| `path` | ltree | materialized path for containment queries |
| `status` | NodeStatus | |
| `version` | int | Context Fabric's own row version, bumped on any update |
| `source_version` | str \| null | vendor's etag/rev, used for freshness diffing |
| `content_hash` | str \| null | hash of the mapped metadata, used for idempotent skip |
| `acl_ref` | dict | opaque pointer resolved by `authorization/` (ADR-007) |
| `attributes` | dict | kind-specific extra fields, not queried structurally |
| `first_seen_at` | datetime | |
| `last_seen_at` | datetime | bumped every sync pass that still finds this object |
| `deleted_at` | datetime \| null | tombstone (ADR set: connector requirements §"Tombstone handling") |
| `created_at` / `updated_at` | datetime | |

Uniqueness: `(source_system, source_instance_id, native_id)` where
`layer='TECHNICAL'` — the idempotency anchor for sync.

## Edge

| Field | Type | Notes |
|---|---|---|
| `id` | UUID | PK |
| `src_id` / `dst_id` | UUID | FK to `node.id` |
| `type` | EdgeType | |
| `origin` | EdgeOrigin | how this edge was created |
| `confidence` | float 0-1 | 1.0 for `HUMAN`/`SYNC_STRUCTURAL`; lower for extracted mentions |
| `state` | EdgeState | `PROPOSED` extracted edges wait for human review in the UI |
| `evidence_id` | UUID \| null | FK to `evidence.id` — where this edge's evidence came from |
| `attributes` | dict | |
| `first_seen_at` / `last_seen_at` | datetime | |
| `deleted_at` | datetime \| null | |

Uniqueness: `(src_id, dst_id, type, origin)`.

## Evidence

| Field | Type | Notes |
|---|---|---|
| `id` | UUID | PK |
| `node_id` | UUID | the node this evidence describes |
| `source_system` / `source_instance_id` / `native_id` | str | provenance |
| `source_version` | str \| null | |
| `uri` | str | deep link back to the source |
| `content_hash` | str \| null | |
| `acl_ref` | dict | inherited by any derived fragment (ADR-007) |
| `retrieved_at` | datetime | |

## ContextSpace (logical layer)

Required fields, as specified:

| Field | Type |
|---|---|
| `id` | str (e.g. `talentflow/identity`) |
| `name` | str |
| `description` | str |
| `owners` | list[str] |
| `product` | str \| null |
| `teams` | list[str] |
| `services` | list[str] |
| `status` | `active` \| `deprecated` |
| `version` | int |
| `created_at` / `updated_at` | datetime |

Plus (needed to make it operable, not just descriptive):

| Field | Type | Notes |
|---|---|---|
| `business_node_id` | UUID | FK to the `node` row (layer=BUSINESS) this space represents |
| `bindings` | list[Binding] | see below |

## Binding

Maps a source-specific native location into a `ContextSpace`. Examples per
spec: ADO project + area path, GitHub repository + file paths, Jira project
+ component, Confluence space + root pages, Notion teamspace + root pages.

| Field | Type | Notes |
|---|---|---|
| `id` | UUID | |
| `context_space_id` | str | FK |
| `capability` | Capability | `configs/capabilities.yaml` |
| `source_system` | str | |
| `source_instance_id` | str | which connector connection |
| `native_container` | str | source-specific location string (e.g. `"acme-org/identity-service"`, `"TalentFlow\Identity"`, `"PLATFORM/Identity"`) |
| `origin` | EdgeOrigin | almost always `HUMAN` |
| `created_at` / `updated_at` | datetime | |

## SyncState

Required fields, as specified:

| Field | Type |
|---|---|
| `source_system` | str |
| `scope_id` | str — the container/connection this cursor tracks |
| `cursor` | str \| null |
| `last_event_id` | str \| null |
| `last_successful_sync` | datetime \| null |
| `last_reconciliation` | datetime \| null |
| `status` | SyncStatus |
| `error` | str \| null |

## SyncRun

Not in the original spec, added for observability (`docs/phases/PHASE-06.md`,
`docs/phases/PHASE-14.md`) — one row per sync invocation, so `sync_state`
can stay a small "current cursor" table while history is queryable.

| Field | Type |
|---|---|
| `id` | UUID |
| `source_system` | str |
| `scope_id` | str |
| `correlation_id` | str |
| `started_at` / `finished_at` | datetime |
| `status` | SyncStatus |
| `nodes_upserted` / `nodes_tombstoned` / `edges_created` | int |
| `error_category` | ErrorCategory \| null |
| `error_detail` | str \| null — never contains credentials or raw content (docs/SECURITY.md) |

## TaskCheckpoint

Required fields, as specified (ADR-008):

| Field | Type |
|---|---|
| `task_ref` | str |
| `stage` | str — matches a key in `configs/stage-contracts.yaml` |
| `objective` | str |
| `context_space_ids` | list[str] |
| `accepted_decisions` | list[str] |
| `completed_actions` | list[str] |
| `files_changed` | list[str] |
| `tests_executed` | list[str] |
| `unresolved_questions` | list[str] |
| `evidence_versions` | dict[str, str] — evidence_id -> source_version at checkpoint time |
| `repository_sha` | str \| null |
| `updated_at` | datetime |

## Connector-facing types

Used by `SourceConnector` implementations (`docs/CONNECTORS.md`); these are
the only shapes a connector may return across its public boundary.

```
SourceContainer   id, name, kind, parent_id, native_id, attributes
SourceObject      native_id, kind, name, parent_native_id, attributes,
                   source_version, content_hash, deleted: bool
SourceContent     native_id, version, mime_type, text | None, uri
SourceLink        from_native_id, target_ref (raw string, e.g. "AB#312"),
                   link_kind ("mentions" | "relates_to" | ...)
ACLReference       native_id, acl_ref: dict (opaque, resolved by authorization/)
Page[T]            items: list[T], next_cursor: str | None
ChangePage         items: list[SourceObject], next_cursor: str | None,
                   has_more: bool
```

## ContextPack (retrieval output)

Not persisted directly (packs are caches, ADR-008) but is a first-class
domain type — the output of `get_context_pack` (`docs/MCP.md`).

```
task, scope, hard_constraints, approved_requirements, accepted_decisions,
relevant_repositories, relevant_changes, tests, conflicts, open_questions,
evidence, freshness, expansion_handles
```

Every populated slot's items carry `evidence_id`s pointing into `evidence`.
See `docs/MCP.md` for the exact JSON shape and `docs/RETRIEVAL.md` for how
each slot gets filled.
