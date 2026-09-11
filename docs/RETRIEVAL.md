# Retrieval

Scope resolution, the context-pack compiler, stage contracts, and token
budgeting. Deterministic throughout (ADR-006) — no embeddings, no
similarity search, no model call. Implemented in Phases 9-10
(`docs/phases/PHASE-09.md`, `PHASE-10.md`).

## 1. Scope resolution

Input: a `task_ref` (e.g. `"AB#312"`) and an `actor_id`.

```
1. Parse task_ref -> (source_system, native_id) via a small per-source
   pattern table (e.g. "AB#" -> azure_devops work item).
2. Look up the corresponding TECHNICAL node.
3. Walk CONTAINS/BELONGS_TO edges upward to collect the full ancestor path
   (this is exactly what `path` (ltree) already encodes — see
   docs/persistence.md).
4. Query `binding` for rows whose (source_system, source_instance_id,
   native_container) is an ancestor of (or equal to) that path.
5. Union the business nodes reached via each matching binding's
   context_space.business_node_id.
6. Derive products / teams / services / repositories from those business
   nodes and their edges (HAS_SERVICE, OWNED_BY, IMPLEMENTED_BY).
7. authorization.filter_visible() over every candidate node before
   returning anything (ADR-007).
```

### Ambiguity

More than one binding can match (nested area paths, overlapping context
spaces). Resolution order, applied deterministically and always returning
every candidate alongside the winner so nothing is silently dropped:

1. **Longest matching `path` wins** — the most specific container beats a
   broader ancestor.
2. **Binding priority** — an explicit `priority` field on `binding`
   (default 0), set by whoever authored it in the UI.
3. **Binding `id`** — stable tiebreaker, lowest UUID.

`resolve_scope` (`docs/MCP.md`) returns the winning scope *and* every
candidate — callers can see when a task_ref is ambiguous rather than
silently getting the "wrong" team's boundary.

## 2. Stage contracts

Pure configuration: `configs/stage-contracts.yaml`. One stage = one
top-level key = a list of slots. A slot:

```yaml
- name: changed_relevant_files
  node_kinds: [FILE]
  capability: CODE
  traversal: { edge_types: [CHANGES, CONTAINS], max_hops: 4, direction: any }
  required: false
  max_items: 30
  token_share: 20
```

The compiler (`retrieval/compiler.py`) is **generic** — it never
special-cases a stage name. It:

1. Loads the contract for `stage` from `configs/stage-contracts.yaml`.
2. For each slot, traverses from the resolved scope's root nodes using the
   slot's `traversal` spec (`graph/traversal.py`), filtered to `node_kinds`
   and (if set) `capability`.
3. Filters the traversal result through `authorization.filter_visible`
   (ADR-007 — before ranking, always).
4. Scores each remaining candidate (see §3) and keeps the top `max_items`.
5. Allocates `token_budget * (slot.token_share / sum(all token_shares))`
   to the slot; if the slot's items don't fit, the lowest-scored items are
   dropped and become `expansion_handles` instead of being silently lost.
6. If a `required: true` slot ends up empty after steps 3-5, it is
   **not** silently omitted — it is surfaced in `conflicts` or
   `open_questions` on the pack (`docs/MCP.md`).

Adding or changing a stage is a YAML change; it never requires touching
`retrieval/compiler.py`.

## 3. Ranking

Every candidate node/edge gets a deterministic score, computed in Python
over data already fetched by SQL (no per-item query):

```
score = w1 * (1 / (1 + edge_distance))
      + w2 * edge_type_weight[edge.type]
      + w3 * (1.0 if node.capability == slot.capability else 0.0)
      + w4 * recency_decay(node.last_seen_at)
      + w5 * origin_weight[edge.origin]     # HUMAN > SYNC_EXTRACTED > SYNC_STRUCTURAL/RULE
```

Weights (`w1..w5`) live in `configs/stage-contracts.yaml` `defaults` or a
sibling `configs/ranking.yaml` if they need to vary per-stage later —
Phase 10 decides which; either way they are configuration, not hardcoded
constants in `compiler.py`.

## 4. Token budgeting

`get_context_pack` takes a `token_budget`. The compiler:

- Splits the budget across slots proportional to `token_share`.
- Within a slot, includes items highest-score-first until the slot's share
  is spent (a simple token estimator — character count / 4 as a first
  pass, documented as an approximation, not a real tokenizer dependency).
- Anything cut for budget becomes an `expansion_handle`: `{evidence_id,
  reason: "token_budget"}`, retrievable later via `expand_evidence`
  without re-running scope resolution.

## 5. Freshness

Each evidence item on a pack carries `source_version` (captured at compile
time) and the slot's `max_age_days`. The pack's `freshness` field
summarizes: per evidence item, `age_days` and whether it exceeds
`max_age_days`. `get_context_pack` does **not** auto-refresh stale evidence
— it flags it; the caller decides whether to call `refresh_evidence`
(`docs/MCP.md`) before an actionable decision, exactly as specified.

## 6. Restart / compaction flow (ADR-008)

```
load task_checkpoint(task_ref)
  -> resolve_scope(task_ref, actor_id)          # re-run, never trusted from before
  -> for each evidence_id in checkpoint.evidence_versions:
         current = persistence.get_node_source_version(evidence_id)
         if current != checkpoint.evidence_versions[evidence_id]:
             refresh_evidence(...)               # re-fetch only this one
  -> get_context_pack(...)                        # compiled fresh, every time
```

A pack is never built by editing or summarizing a previous pack — it is
always compiled from current graph state plus the checkpoint's bookkeeping
fields. See ADR-008 "a summary is never recursively re-summarized."

## 7. What retrieval never does

Call an LLM. Call a connector directly (`AGENTS.md` §5 — it only reads what
`synchronization/` already persisted; `expand_evidence`/`refresh_evidence`
re-enter through synchronization, they don't shortcut into `connectors/`
from `retrieval/`). Guess an ambiguous scope silently. Return a fact without
an `evidence_id`. Skip authorization filtering "because it's just fixture
data."
