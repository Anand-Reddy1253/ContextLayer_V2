# ADR-008: Task checkpoints as durable state; conversation history is not

## Status
Accepted

## Context
Agent conversations get summarized, compacted, or restarted. If the only
record of "what stage is this task at, what's been decided, what files
changed" lives in conversation history, it is lost or degraded exactly when
it matters most — across a restart or a long-running task.

## Decision
A `task_checkpoint` row (`docs/DOMAIN_MODEL.md`) is the durable record of
task progress: `task_ref`, `stage`, `objective`, `context_space_ids`,
`accepted_decisions`, `completed_actions`, `files_changed`,
`tests_executed`, `unresolved_questions`, `evidence_versions`,
`repository_sha`, `updated_at`. On restart or compaction, the sequence is
fixed: load the checkpoint → re-resolve scope → diff stored
`evidence_versions` against current `source_version` → refresh only what
changed → recompile a new pack (`docs/RETRIEVAL.md` "Freshness").

Generated context packs and summaries are caches, never sources of truth.
**A summary is never recursively re-summarized** — each pack is compiled
fresh from the graph and the checkpoint, not from a previous pack's prose.

## Consequences
- Losing conversation history is recoverable; losing the checkpoint is not
  — checkpoints must be written proactively as a task progresses, not only
  at session end.
- "Refresh only what changed" means the freshness check is a version diff,
  not a full recompile-everything pass — this keeps restarts cheap.
- Anything that looks like "summarize this summary" in a future feature
  request should be rejected at design time per this ADR.
