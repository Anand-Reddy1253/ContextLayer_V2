"""Deterministic scope resolution (docs/RETRIEVAL.md §1) — the first
stage of retrieval: task_ref -> context space -> products/teams/services/
repositories, fully traceable and never guessed.

Deviation from docs/RETRIEVAL.md §1 step 6, noted rather than hidden:
the doc describes deriving products/teams/services from business nodes
via HAS_SERVICE/OWNED_BY/IMPLEMENTED_BY edges — but nothing in this
codebase ever creates those edges (catalog/business_tree.py seeds
BUSINESS nodes with no edges of their own; ContextSpace already carries
product/teams/services as flat fields set at authoring time, same
precedent as Phase 8's product/products fix). Reading them directly off
the winning ContextSpace is simpler and is what the data actually
contains — a graph walk here would have nothing to walk. `repositories`
is genuinely derived: every CODE-capability binding's native_container
on the winning context space.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict

from context_fabric.domain.context_space import Binding
from context_fabric.domain.enums import Capability
from context_fabric.persistence.repositories.context_space import ContextSpaceRepository
from context_fabric.persistence.repositories.node import NodeRepository
from context_fabric.retrieval.task_ref import UnrecognizedTaskRef, parse_task_ref


class BindingCandidate(BaseModel):
    """One binding whose resolved native_container is an ancestor-or-self
    of the target object's path — a context space claiming this task_ref
    falls in its boundary. Every candidate is kept, not just the winner,
    so ambiguity is visible rather than silently resolved
    (docs/RETRIEVAL.md §1 "Ambiguity")."""

    model_config = ConfigDict(extra="forbid")

    binding: Binding
    context_space_id: str
    matched_path: str
    match_depth: int


class ScopeResolution(BaseModel):
    """Phase 1 deferred `ContextPack.task`/`.scope`'s concrete shape to
    this phase (domain/context_pack.py) — this is that shape. Wiring it
    into ContextPack itself is Phase 10's job (the compiler is the first
    actual consumer); this phase's exit gate is resolve_scope tested
    directly, not integrated yet."""

    model_config = ConfigDict(extra="forbid")

    task_ref: str
    actor_id: str
    resolved: bool
    reason: str | None = None

    source_system: str | None = None
    native_id: str | None = None
    node_id: UUID | None = None

    context_space_id: str | None = None
    product: str | None = None
    teams: list[str] = []
    services: list[str] = []
    repositories: list[str] = []

    # Winner-first (candidates[0] is the resolved scope above) — every
    # matching binding, so a caller can see when a task_ref was ambiguous
    # rather than silently getting one team's boundary.
    candidates: list[BindingCandidate] = []


def _is_ancestor_or_self(ancestor_path: str, path: str) -> bool:
    """ltree "is ancestor of or equal to" — done in Python on strings
    already in memory (both sides come from a get_by_technical_identity
    lookup this function already made) rather than a second DB round
    trip per binding."""
    return path == ancestor_path or path.startswith(f"{ancestor_path}.")


async def resolve_scope(
    node_repo: NodeRepository,
    context_space_repo: ContextSpaceRepository,
    task_ref: str,
    actor_id: str,
    context_space_override: str | None = None,
) -> ScopeResolution:
    """Implements docs/RETRIEVAL.md §1's 6-step algorithm. Every failure
    mode (unparseable task_ref, never-synced object, no covering binding)
    returns `resolved=False` with a `reason` — never an exception, never
    a silent empty success that looks the same as "resolved to nothing."
    """
    try:
        parsed = parse_task_ref(task_ref)
    except UnrecognizedTaskRef as exc:
        return ScopeResolution(
            task_ref=task_ref, actor_id=actor_id, resolved=False, reason=str(exc)
        )

    # Step 2: the corresponding TECHNICAL node.
    target = await node_repo.get_by_technical_identity_any_instance(
        parsed.source_system, parsed.native_id
    )
    if target is None:
        return ScopeResolution(
            task_ref=task_ref,
            actor_id=actor_id,
            resolved=False,
            reason=f"no synced technical node for {parsed.source_system}:{parsed.native_id}",
            source_system=parsed.source_system,
            native_id=parsed.native_id,
        )

    # Step 3: the full ancestor path is already encoded in target.path
    # (ltree) — nothing further to compute, per docs/RETRIEVAL.md §1.

    # Step 4-5: bindings whose native_container resolves to an ancestor-
    # or-self of target.path, unioned across whichever context spaces are
    # in play (all of them, unless the caller already knows which one).
    spaces = await context_space_repo.list_all()
    if context_space_override is not None:
        spaces = [s for s in spaces if s.id == context_space_override]

    candidates: list[BindingCandidate] = []
    for space in spaces:
        for binding in space.bindings:
            binding_node = await node_repo.get_by_technical_identity(
                binding.source_system, binding.source_instance_id, binding.native_container
            )
            if binding_node is None:
                # An unsynced/unreconciled binding — same "not resolved
                # yet" case catalog.reconcile_context_space already
                # treats as non-fatal, not a hard failure here either.
                continue
            if _is_ancestor_or_self(binding_node.path, target.path):
                candidates.append(
                    BindingCandidate(
                        binding=binding,
                        context_space_id=space.id,
                        matched_path=binding_node.path,
                        match_depth=binding_node.path.count(".") + 1,
                    )
                )

    if not candidates:
        return ScopeResolution(
            task_ref=task_ref,
            actor_id=actor_id,
            resolved=False,
            reason="no context space binding covers this object's ancestry",
            source_system=parsed.source_system,
            native_id=parsed.native_id,
            node_id=target.id,
        )

    # Ambiguity tiebreak (docs/RETRIEVAL.md §1): longest matching path
    # wins, then binding priority (higher wins), then binding id (lowest
    # UUID) — a single min() key encodes all three by negating the two
    # "higher wins" fields so the smallest tuple is always the winner.
    candidates.sort(key=lambda c: (-c.match_depth, -c.binding.priority, c.binding.id))
    winner = candidates[0]
    winning_space = next(s for s in spaces if s.id == winner.context_space_id)

    repositories = [
        b.native_container for b in winning_space.bindings if b.capability == Capability.CODE
    ]

    # --- Phase 11 seam (docs/phases/PHASE-09.md) ---------------------
    # authorization/ doesn't exist yet. Once it does, this is where
    # candidates (and target) get filtered:
    #   candidates = [c for c in candidates
    #                 if await authorization.can_read(actor_id, c-derived acl_ref)]
    # before anything below is returned — never as a post-filter on an
    # already-compiled result (docs/SECURITY.md). Deliberately a visible
    # pass-through, not a silently-finished no-op.
    # ------------------------------------------------------------------

    return ScopeResolution(
        task_ref=task_ref,
        actor_id=actor_id,
        resolved=True,
        source_system=parsed.source_system,
        native_id=parsed.native_id,
        node_id=target.id,
        context_space_id=winning_space.id,
        product=winning_space.product,
        teams=winning_space.teams,
        services=winning_space.services,
        repositories=repositories,
        candidates=candidates,
    )
