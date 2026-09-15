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

It returns `kinds`, `properties` (attribute keys per kind), `relations`, and
`meta_properties`.

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
→ [{"$source":"azure_devops","count":101},{"$source":"github","count":37}]
```

That answer spans two vendors at once — neither tool's own MCP server can
produce it.

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

## Known limits — say so rather than inventing

- **No cross-tool links yet.** PR → work item edges do not exist in this
  catalog, so "which stories have a PR" is unanswerable. Don't infer it from
  name similarity.
- **No deployments.** Deployment frequency and DORA metrics have no data
  behind them.
- **`aggregate_entities` counts only** — no averages or computed intervals, so
  PR cycle time isn't available even though the timestamps are.
- **Everything is read-only.** To comment on a PR or edit an issue, use that
  vendor's own MCP server so the action is attributed to the real actor.
