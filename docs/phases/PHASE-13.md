# Phase 13 — Task checkpoints and freshness

## Goal
Implement `docs/DOMAIN_MODEL.md` "TaskCheckpoint" persistence and the
restart/compaction flow from `docs/RETRIEVAL.md` §6 (ADR-008).

## Inputs
- `docs/RETRIEVAL.md` §5 "Freshness" and §6 "Restart / compaction flow".
- `persistence/repositories/` (Phase 2) already has
  `TaskCheckpointRepository` scaffolded — fill in real usage.
- `mcp/tools.py` (Phase 12) — `refresh_evidence` already exists; this
  phase is what actually calls it as part of a restart flow, and adds
  checkpoint read/write around the MCP tools.

## Files to create
- `retrieval/checkpoint.py` — `load_checkpoint`, `save_checkpoint`,
  `resume_task(task_ref, actor_id)` implementing the exact sequence from
  `docs/RETRIEVAL.md` §6: load checkpoint -> re-resolve scope -> diff
  `evidence_versions` against current `source_version` -> refresh only
  what changed -> compile a new pack.
- `retrieval/freshness.py` — per-evidence `age_days` /
  `exceeds_max_age` computation feeding `ContextPack.freshness`
  (`docs/RETRIEVAL.md` §5), used by both the normal compile path (Phase
  10) and the resume path here.
- Extend `mcp/tools.py` (or add a fifth internal, non-exposed helper) so
  `get_context_pack` writes/updates a checkpoint after compiling, and
  `resume_task` is callable by `cli/` or a future MCP tool if one is added
  later — this phase does not add a new public MCP tool, the four from
  `docs/MCP.md` are the complete public surface.

## Acceptance criteria
- A checkpoint saved mid-task, then loaded via `resume_task`, produces a
  freshly *compiled* pack (not the old cached one) — verify by mutating
  the underlying fixture data (or a synced node) between save and resume
  and confirming the new pack reflects the change.
- `evidence_versions` diffing only triggers `refresh_evidence` for items
  whose `source_version` actually changed — a test proves an unchanged
  item is not re-fetched (same assertion style as Phase 12's
  `refresh_evidence` test, one level up the call stack).
- No code path recursively summarizes a previous pack's content into the
  new one — the new pack is compiled from graph state + checkpoint
  bookkeeping fields only (ADR-008). This is checked by ensuring
  `compile_context_pack`'s signature never accepts a previous
  `ContextPack` as input.

## Tests to write
`tests/integration/retrieval/test_checkpoint_resume.py` — the full
save -> mutate -> resume -> verify-fresh-pack flow.

## Exit gate
`pytest tests/integration/retrieval/test_checkpoint_resume.py -q` green.
