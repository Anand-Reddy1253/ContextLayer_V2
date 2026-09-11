"""Node — the single table backing all three layers (ADR-002).

docs/DOMAIN_MODEL.md "Node": layer-specific validation (a TECHNICAL node
must carry source_system/native_id; BUSINESS/LOGICAL must not) is enforced
here, in the domain model, not by three separate table shapes.
"""

from __future__ import annotations

import re
from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from context_fabric.domain.enums import Capability, Layer, NodeStatus

_LTREE_LABEL = re.compile(r"^[A-Za-z0-9_]+$")


def _validate_path(path: str) -> str:
    if not path:
        raise ValueError("path must not be empty")
    labels = path.split(".")
    for label in labels:
        if not _LTREE_LABEL.match(label):
            raise ValueError(
                f"invalid ltree label {label!r} in path {path!r}: "
                "labels must match [A-Za-z0-9_]+"
            )
    return path


class Node(BaseModel):
    model_config = ConfigDict(frozen=False, extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    layer: Layer
    kind: str
    capability: Capability | None = None
    name: str
    description: str | None = None
    owners: list[str] = Field(default_factory=list)

    source_system: str | None = None
    source_instance_id: str | None = None
    native_id: str | None = None

    parent_id: UUID | None = None
    path: str

    status: NodeStatus = NodeStatus.ACTIVE
    version: int = 1
    source_version: str | None = None
    content_hash: str | None = None

    acl_ref: dict = Field(default_factory=dict)
    attributes: dict = Field(default_factory=dict)

    first_seen_at: datetime
    last_seen_at: datetime
    deleted_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def _validate_path_shape(self) -> Node:
        _validate_path(self.path)
        return self

    @model_validator(mode="after")
    def _validate_layer_identity(self) -> Node:
        technical_fields_set = any(
            v is not None for v in (self.source_system, self.native_id)
        )
        if self.layer is Layer.TECHNICAL:
            if self.source_system is None or self.native_id is None:
                raise ValueError(
                    "TECHNICAL nodes require source_system and native_id"
                )
        else:
            if technical_fields_set:
                raise ValueError(
                    f"{self.layer} nodes must not set source_system/native_id"
                    " (technical-only identity fields)"
                )
        return self
