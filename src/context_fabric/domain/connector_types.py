"""Connector-facing types (docs/DOMAIN_MODEL.md "Connector-facing types").

These are the only shapes a SourceConnector implementation may return
across its public boundary (docs/CONNECTORS.md, AGENTS.md §5) — no vendor
SDK object or raw vendor dict may cross out of connectors/mapper.py.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

LinkKind = Literal["mentions", "relates_to", "verifies", "depends_on"]


class SourceContainer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    kind: str
    parent_id: str | None = None
    native_id: str
    attributes: dict = Field(default_factory=dict)
    # A short, vendor-supplied summary (ADR-003 already lists "description"
    # as intended metadata; this field just wires it up). Bounded — a real
    # one-line vendor description, never a body. None when the vendor has
    # no such field for this object type.
    description: str | None = None


class SourceObject(BaseModel):
    model_config = ConfigDict(extra="forbid")

    native_id: str
    kind: str
    name: str
    parent_native_id: str | None = None
    attributes: dict = Field(default_factory=dict)
    source_version: str | None = None
    content_hash: str | None = None
    deleted: bool = False
    # See SourceContainer.description — same field, same bound.
    description: str | None = None


class SourceContent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    native_id: str
    version: str | None = None
    mime_type: str
    text: str | None = None
    uri: str


class SourceLink(BaseModel):
    model_config = ConfigDict(extra="forbid")

    from_native_id: str
    target_ref: str
    link_kind: LinkKind = "mentions"
    # Why this link was proposed, human-readable, shown to the reviewer
    # in the Proposed Links queue so a confirm/reject decision isn't made
    # blind (docs/UI.md "Proposed links review queue") — either the
    # vendor-native relation type that produced it (structured, no
    # text to quote) or the actual matched text snippet (regex-mined
    # from a body/description, so the reviewer sees exactly what
    # triggered the match, not just the conclusion).
    evidence: str | None = None


class ACLReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    native_id: str
    acl_ref: dict = Field(default_factory=dict)


class Page[T](BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[T] = Field(default_factory=list)
    next_cursor: str | None = None


class ChangePage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[SourceObject] = Field(default_factory=list)
    next_cursor: str | None = None
    has_more: bool = False
