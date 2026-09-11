# Team Contexts

UI label: "Team Contexts". Internal/code identifiers (ContextSpace,
context-spaces routes, this folder) are unchanged — only the user-facing
name changed.

Logical-layer authoring: create/edit a ContextSpace, attach it to a
business node, and manage its bindings (capability -> connector instance ->
native container), mirroring the shape in
configs/context-spaces/talentflow-identity.yaml. This is the screen where a
human draws the boundary an agent later resolves through
`resolve_scope` (docs/MCP.md).

v1 also surfaces `PROPOSED` extracted edges (origin=SYNC_EXTRACTED) for a
human to confirm/reject/retype — see docs/UI.md "Proposed links review".

Implemented in Phase 16 (docs/phases/PHASE-16.md).
