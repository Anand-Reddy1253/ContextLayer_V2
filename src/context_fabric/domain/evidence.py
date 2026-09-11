"""Evidence — provenance for every fact a context pack returns.

docs/DOMAIN_MODEL.md "Evidence". Derived fragments inherit acl_ref
unchanged from the evidence they were built from (docs/SECURITY.md,
ADR-007) — enforced by callers, not by this model, since a plain model
can't see "where a fragment came from."
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    node_id: UUID
    source_system: str
    source_instance_id: str
    native_id: str
    source_version: str | None = None
    uri: str
    content_hash: str | None = None
    acl_ref: dict = Field(default_factory=dict)
    retrieved_at: datetime
