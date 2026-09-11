"""ContextSpace and Binding — the logical layer (docs/DOMAIN_MODEL.md).

A ContextSpace is the human decision that binds a business scope to
source-specific native locations across connectors, by capability. This is
what turns a team name into a searchable boundary (docs/architecture.md).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from context_fabric.domain.enums import Capability, EdgeOrigin

ContextSpaceStatus = Literal["active", "deprecated"]


class Binding(BaseModel):
    """Maps a source-specific native location into a ContextSpace. Examples:
    ADO project + area path, GitHub repository + file paths, Jira project +
    component, Confluence space + root pages, Notion teamspace + root pages.
    """

    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    context_space_id: str
    capability: Capability
    source_system: str
    source_instance_id: str
    native_container: str
    origin: EdgeOrigin = EdgeOrigin.HUMAN
    # Ambiguity tiebreak, second tier after longest-matching-path
    # (docs/RETRIEVAL.md §1 "Ambiguity"): set by whoever authors the
    # binding in the UI. Added in Phase 9 — docs/RETRIEVAL.md assumed
    # this field from the start, but the Phase 1 domain model and Phase 2
    # schema (both also Phase 0 output) omitted it; scope resolution is
    # the first thing that actually needed it to exist.
    priority: int = 0
    created_at: datetime
    updated_at: datetime


class ContextSpace(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    description: str
    owners: list[str] = Field(default_factory=list)
    product: str | None = None
    teams: list[str] = Field(default_factory=list)
    services: list[str] = Field(default_factory=list)
    status: ContextSpaceStatus = "active"
    version: int = 1
    created_at: datetime
    updated_at: datetime

    # Needed to make it operable, not just descriptive (docs/DOMAIN_MODEL.md).
    business_node_id: UUID
    bindings: list[Binding] = Field(default_factory=list)
