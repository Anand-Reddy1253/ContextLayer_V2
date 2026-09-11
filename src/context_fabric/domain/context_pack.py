"""ContextPack — the output of get_context_pack (docs/MCP.md,
docs/RETRIEVAL.md).

Every populated slot's items carry an evidence_id present in the pack's
`evidence` list (docs/DOMAIN_MODEL.md "ContextPack") — no fact is ever
returned without traceable provenance. `task`/`scope` stay loosely typed
(dict) here: their concrete shape is produced by retrieval/scope.py in
Phase 9 and isn't pinned down by any Phase-1 consumer yet; tightening them
into a dedicated type is a Phase 9 decision, not a Phase 1 one.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from context_fabric.domain.evidence import Evidence


class ContextPackItem(BaseModel):
    """One fact placed into a context-pack slot."""

    model_config = ConfigDict(extra="forbid")

    node_id: UUID
    evidence_id: UUID
    kind: str
    name: str
    uri: str | None = None
    attributes: dict = Field(default_factory=dict)


class ExpansionHandle(BaseModel):
    """A fact cut for token budget, retrievable later via expand_evidence
    without re-running scope resolution (docs/RETRIEVAL.md §4)."""

    model_config = ConfigDict(extra="forbid")

    evidence_id: UUID
    reason: str


class FreshnessEntry(BaseModel):
    """Per-evidence age, and whether it exceeds the stage contract slot's
    max_age_days (docs/RETRIEVAL.md §5)."""

    model_config = ConfigDict(extra="forbid")

    evidence_id: UUID
    age_days: float
    exceeds_max_age: bool


class ContextPack(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    task: dict = Field(default_factory=dict)
    scope: dict = Field(default_factory=dict)

    hard_constraints: list[ContextPackItem] = Field(default_factory=list)
    approved_requirements: list[ContextPackItem] = Field(default_factory=list)
    accepted_decisions: list[ContextPackItem] = Field(default_factory=list)
    relevant_repositories: list[ContextPackItem] = Field(default_factory=list)
    relevant_changes: list[ContextPackItem] = Field(default_factory=list)
    tests: list[ContextPackItem] = Field(default_factory=list)

    conflicts: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)

    evidence: list[Evidence] = Field(default_factory=list)
    freshness: list[FreshnessEntry] = Field(default_factory=list)
    expansion_handles: list[ExpansionHandle] = Field(default_factory=list)

    created_at: datetime
