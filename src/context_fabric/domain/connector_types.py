"""Connector-facing types (docs/DOMAIN_MODEL.md "Connector-facing types").

These are the only shapes a SourceConnector implementation may return
across its public boundary (docs/CONNECTORS.md, AGENTS.md §5) — no vendor
SDK object or raw vendor dict may cross out of connectors/mapper.py.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# "implements" / "specifies" / "changes" carry more meaning than a bare
# mention, and which one applies depends on *where* a reference was found
# (connectors/cross_references.py's LINK_KIND_BY_LOCATION): a work item id
# in a pull request title is the author saying "this PR does that work";
# the same id in a review comment is a passing mention. EdgeType already
# had IMPLEMENTS/SPECIFIED_BY/CHANGES defined and unused — every extracted
# link used to collapse to MENTIONS/RELATED_TO no matter its source.
LinkKind = Literal[
    "mentions", "relates_to", "verifies", "depends_on", "implements", "specifies", "changes"
]


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
    # How reliable this specific link is, source-dependent — a vendor's
    # own structured field (a build's `repository.id`, ADO's own relation
    # API, Confluence's own page-link macro) is a stated fact, not a
    # guess, and gets 1.0; a regex match against free text is inherently
    # a guess and keeps the historical default. synchronization/
    # link_extraction.py auto-confirms (state=ACTIVE, origin=
    # SYNC_STRUCTURAL) anything at or above 0.95 instead of queuing it
    # for human review — real user report: every one of a project's
    # builds proposing "this build's own repository.id field" sat in the
    # same review queue as an actual text-mined guess, even though it's
    # exactly as certain as the structural CONTAINS hierarchy is.
    confidence: float = 0.7
    # Emit the edge pointing *at* the node being processed rather than out
    # of it. A connector only ever gets asked "what links come out of node
    # X", so a vendor relation whose natural reading runs the other way has
    # no other way to be expressed correctly. Real case: Azure DevOps's
    # "Tested By" relation sits on the work item and names the test case,
    # which means "that test case verifies this work item" — emitted
    # forward it produced 93 edges reading STORY --VERIFIES--> TEST_CASE,
    # i.e. every one backwards. synchronization/link_extraction.py swaps
    # src/dst when this is set.
    reverse: bool = False


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
