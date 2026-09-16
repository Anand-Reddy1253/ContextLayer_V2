"""WorkflowTemplate and WorkflowStep — a named, ordered sequence of steps
a harness pulls and executes (docs/MCP.md's "harness composition" note on
`resolve_scope`). Context Fabric never runs a template; it only stores and
serves it, same read-only boundary as everything else this project
exposes (AGENTS.md §4/§6).

Same shape as ContextSpace + Binding (domain/context_space.py) on purpose:
a parent row with an ordered list of child rows, authored once and reused.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

WorkflowTemplateStatus = Literal["active", "deprecated"]


class WorkflowStep(BaseModel):
    """One step: a specific AI_ASSET node picked from the catalog at
    author time. `label`/`vendor`/`asset_type` are snapshotted then —
    same reasoning as Binding.native_container storing the container
    directly rather than a live join — so a template still displays and
    is usable even if the underlying repo is later unsynced; whether the
    node still resolves is a reconcile-style check, not a rendering
    dependency."""

    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    workflow_template_id: UUID
    order: int
    source_system: str
    source_instance_id: str
    native_id: str
    label: str
    vendor: str
    asset_type: str
    instructions: str | None = None
    created_at: datetime
    updated_at: datetime


class WorkflowTemplate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    context_space_id: str
    name: str
    description: str = ""
    status: WorkflowTemplateStatus = "active"
    created_at: datetime
    updated_at: datetime

    steps: list[WorkflowStep] = Field(default_factory=list)
