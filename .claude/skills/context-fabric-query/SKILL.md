---
name: context-fabric-query
description: Query the Context Fabric catalog — work items, pull requests, builds, pages, repos and AI assets synced from Azure DevOps, GitHub and Confluence. Use when asked about engineering work across tools, ownership, freshness, test coverage, or anything needing a structured filter or a count across systems.
---

# Querying Context Fabric

Context Fabric is a catalog of engineering entities synced from several tools
into one graph. It stores **metadata, not content** — enough to find, filter and
relate things, with a `locator` on every result for fetching the full object
from the vendor's own MCP server.

Use it when a question spans tools, needs a count, or asks what's *missing*.
Use the vendor's own MCP server when you need the body of one known object.

## Always call `describe_schema` first

Kinds are not a fixed vocabulary — they are whatever has been synced. Guessing a
kind name is the most common way to get an empty result that looks like a real
answer.

```
describe_schema()              → every kind, its properties, and relation types
describe_schema(kind="STORY")  → just that one
```

It returns `kinds` (nested `{source: {kind: count}}` — read this per-source, not
as one flat list — see below), `properties` (attribute *keys* per kind, not
their values — see "Kind vs. label" below), `relations`, and `meta_properties`.

### Kind vs. label/attribute value — the same word means different things per vendor

The same real-world concept ("a bug") is a first-class **kind** in some
systems and only a **label or attribute value** in others — `describe_schema`'s
`kinds` is the only reliable way to tell which, per source, before you write a
query:

- Jira/Azure DevOps model bugs as a real, structured kind: `$blueprint = "BUG"`
  is a valid, efficient filter there.
- GitHub has **no** `BUG` kind at all — only `ISSUE` and `PULL_REQUEST`. "Bug"
  only ever shows up as a **label** on an `ISSUE` (`{"property": "labels",
  "operator": "containsAny", "value": ["bug"]}`), never as `$blueprint`.

Querying `$blueprint = "BUG"` scoped to GitHub returns a clean `matched: 0` —
**check the response's `warnings` key before trusting that zero.** When a
query names a `$blueprint` that doesn't exist at all, or doesn't exist for the
`$source` it's paired with, `search_entities`/`aggregate_entities` add a
`warnings` entry explaining exactly that (which sources the kind *does* exist
for, and what kinds the source you asked about actually has instead) — a bare
`matched: 0` / empty `results` with **no** `warnings` key means the zero is
real. Never assume a kind name from one vendor applies to another; check
`properties` (which attribute *keys* exist, e.g. `labels`) and, if you need to
know what *values* a key actually holds (is "bug" really a label anyone
used?), run a discovery query first — e.g. `aggregate_entities(group_by=
["labels"])` — rather than guessing a value and trusting silence.

## Query shape

A query is a rule group. Groups nest, so `and` and `or` compose freely.

```json
{"combinator": "and", "rules": [
  {"property": "$blueprint", "operator": "=",  "value": "STORY"},
  {"property": "state",      "operator": "!=", "value": "Done"}
]}
```

Pass it to `search_entities(query, limit)` as a JSON string.

### Properties

`$`-prefixed properties are universal; everything else is an attribute key from
`describe_schema`.

| property | meaning |
|---|---|
| `$blueprint` | the kind (`STORY`, `PULL_REQUEST`, `PAGE`, …) |
| `$title` | display name |
| `$identifier` | the vendor's own id |
| `$source` | `azure_devops`, `github`, `confluence` |
| `$path` | position in the hierarchy (see below) |
| `$createdAt` / `$updatedAt` | **the vendor's** timestamps |
| `$syncedAt` | when *we* last synced it |

**`$updatedAt` and `$syncedAt` are not interchangeable.** `$syncedAt` reflects
our sync schedule, not any real activity — every node updates on every run.
Always use `$updatedAt` for "what changed", "what's stale", "recent work".

### Operators

| kind | operators |
|---|---|
| equality | `=`, `!=` |
| string | `contains`, `doesNotContain`, `beginsWith`, `endsWith` |
| list | `in`, `notIn`, `containsAny` |
| ordering | `>`, `>=`, `<`, `<=`, `between`, `notBetween` |
| existence | `isEmpty`, `isNotEmpty` |

`!=` also matches entities where the property is absent — `state != "Done"`
includes items with no state at all, which is almost always what's meant.

### Hierarchy

`$path` holds an entity's place in the containment tree
(`DevOnHire.141.324` = story 324, under feature 141, in project DevOnHire).
`beginsWith` on `$path` means "everything underneath":

```json
{"property": "$path", "operator": "beginsWith", "value": "DevOnHire.141"}
```

Results carry `path`, so **you already have the ancestor chain** — don't query
for parents separately.

### Relations

```json
{"relation": "VERIFIES", "operator": "relatedTo",
 "value": "324", "direction": "upstream", "maxHops": 1}
```

- `direction`: `upstream` (things pointing at it), `downstream` (things it
  points at), `both`
- `notRelatedTo` finds what's **missing** — stories with no test coverage,
  repos with no owner. These are questions no single vendor can answer.

## Counting

Never fetch rows to count them. `aggregate_entities(query, group_by)` does it in
one call:

```
aggregate_entities(
  query='{"rules":[{"property":"$blueprint","operator":"=","value":"PULL_REQUEST"}]}',
  group_by=["$source"])
→ {"results": [{"$source":"azure_devops","count":101},{"$source":"github","count":37}],
   "warnings": []}
```

That answer spans two vendors at once — neither tool's own MCP server can
produce it. The response is always `{"results": [...], "warnings": [...]}`,
never a bare array — `warnings` is present (possibly empty) so an empty
`results` is never ambiguous between "genuinely zero" and "the `$blueprint`
you filtered/grouped by doesn't apply to the `$source` in question" (see
"Kind vs. label" above — this is the same trap `search_entities` has, and the
same fix).

## Reading the response

```jsonc
{
  "rollup":  {"matched": 12, "by_kind": {...}, "by_state": {...}},
  "anchors": [{"ref": "n3"}],
  "nodes":   {"n3": {"kind": "STORY", "name": "...", "path": "...",
                     "state": "Done", "locator": {...}}},
  "edges":   [{"src": "n3", "type": "IMPLEMENTS", "dst": "n7"}]
}
```

- **`rollup` first.** For "what's the status of X", the counts often *are* the
  answer — no need to read the nodes at all.
- **`nodes` is a shared dictionary**; anchors and edges reference it by short
  id. Each node appears once.
- **`edges` are semantic only.** Hierarchy is in `path`, never repeated as
  edges.
- **`locator`** on anchors gives `source_system` + `native_id` + `url` for
  handing off to the vendor's MCP server.
- **`warnings` (only present when `rollup.matched` is 0).** If present, your
  query's own `$blueprint` assumption was wrong for at least one `$source` it
  was paired with — read it before concluding the answer is a real zero (see
  "Kind vs. label" above). No `warnings` key at all means the zero is real.

## Worked examples

```jsonc
// High-priority work still open
{"combinator":"and","rules":[
  {"property":"$blueprint","operator":"in","value":["STORY","TASK","BUG"]},
  {"property":"priority","operator":"<=","value":"2"},
  {"property":"state","operator":"!=","value":"Done"}]}

// Unassigned work
{"combinator":"and","rules":[
  {"property":"$blueprint","operator":"in","value":["STORY","TASK"]},
  {"property":"assigned_to","operator":"isEmpty"}]}

// Which test cases verify a story
{"rules":[{"relation":"VERIFIES","operator":"relatedTo",
           "value":"324","direction":"upstream"}]}

// Documentation going stale
{"combinator":"and","rules":[
  {"property":"$blueprint","operator":"=","value":"PAGE"},
  {"property":"$updatedAt","operator":"<","value":"2026-01-01"}]}

// Open work in one feature, either state
{"combinator":"and","rules":[
  {"property":"$path","operator":"beginsWith","value":"DevOnHire.141"},
  {"combinator":"or","rules":[
    {"property":"state","operator":"=","value":"In Progress"},
    {"property":"state","operator":"=","value":"Approved"}]}]}
```

## Finding what's available to run for a task (harness composition)

Context Fabric never executes anything — it only answers "what's there and
where." A harness (you, running a task) composes two calls to go from a
task reference to a runnable agent/skill definition:

**1. Resolve scope** — which repo/team/product a task belongs to:

```
resolve_scope(task_ref="AB#312", actor_id="you")
→ {"resolved": true, "product": "talentflow", "teams": ["identity-squad"],
   "repositories": ["acme-org/identity-service"], ...}
```

`task_ref` accepts an Azure DevOps ref (`AB#312`), a Jira key
(`TALENT-42`), a GitHub issue/PR ref (`owner/repo#7`), or a Confluence page
ref (`CONFPAGE-98765`). A task_ref that was never synced, or has no
covering context-space binding, comes back `resolved: false` with a
`reason` — check it before assuming `repositories` is usable.

**2. Search for AI assets in that scope** — agent/skill/rule definitions a
repository declares (`.github/agents/`, `.claude/skills/`, `.cursor/rules/`,
etc. — GitHub and Azure DevOps repos both get scanned for these when their
connection has the `ai_assets` entity type enabled):

```
search_entities(query='{"combinator":"and","rules":[
  {"property":"$blueprint","operator":"=","value":"AI_ASSET"},
  {"property":"$path","operator":"beginsWith","value":"<repository path>"}]}')
```

Each result's `locator` names the vendor and the asset's own path
(`attributes.vendor`, `attributes.asset_type` — agent/skill/prompt/rule/
command). To actually run one, fetch its full definition via that
connector's own on-demand content locator (not stored in the catalog —
ADR-003), then execute it yourself; Context Fabric holds no write path and
never runs an agent on a caller's behalf.

This is the same two-call "resolve scope, then query within it" shape as
any other scoped question — nothing here is a special "workflow" endpoint.

## Known limits — say so rather than inventing

- **Cross-tool links are real but sparse, and only ever weak `MENTIONS`.**
  Confirmed live: a Jira ticket can `MENTIONS` a GitHub PR, a Confluence page
  can `MENTIONS` an Azure DevOps task — but there is no cross-vendor
  `IMPLEMENTS`/`CHANGES` (the stronger, structured "this PR implements that
  ticket" link is same-vendor only today). So "which stories have a PR" is
  answerable only as "which stories are *mentioned by* a PR" via a `MENTIONS`
  `relatedTo` query, not as a reliable implements/closes relationship — don't
  infer the latter from a `MENTIONS` edge or from name similarity.
- **No deployments.** Deployment frequency and DORA metrics have no data
  behind them.
- **`aggregate_entities` isn't count-only** — `metrics` also supports `avg`,
  `sum`, `min`, `max` (need `property`), and `avg_duration_days` (needs
  `start`/`end` — the metric that actually answers "average PR cycle time",
  since a plain `avg` can't express an interval between two timestamps). See
  the "Counting" section's worked example for the default (count) shape.
- **`isEmpty`/`isNotEmpty` are unreliable on list-valued properties** (e.g.
  `labels`) — confirmed live: `{"property":"labels","operator":"isEmpty"}`
  returned 0 matches against a set where the true count was 13. For a list
  property, use `aggregate_entities(group_by=["labels"])` and check for an
  absent/empty group instead of trusting `isEmpty` directly; this operator is
  fine on scalar properties (`assigned_to`, `description`).
- **Everything is read-only.** To comment on a PR or edit an issue, use that
  vendor's own MCP server so the action is attributed to the real actor.
