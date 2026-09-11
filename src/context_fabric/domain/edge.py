"""Edge — typed, directional relationships between nodes.

docs/DOMAIN_MODEL.md "Edge". Uniqueness on (src_id, dst_id, type, origin)
is a persistence-layer constraint (docs/persistence.md), not re-validated
here — the domain model only validates what's true of a single row.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from context_fabric.domain.enums import EdgeOrigin, EdgeState, EdgeType


class Edge(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    src_id: UUID
    dst_id: UUID
    type: EdgeType
    origin: EdgeOrigin
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    state: EdgeState = EdgeState.ACTIVE
    evidence_id: UUID | None = None
    attributes: dict = Field(default_factory=dict)

    first_seen_at: datetime
    last_seen_at: datetime
    deleted_at: datetime | None = None
