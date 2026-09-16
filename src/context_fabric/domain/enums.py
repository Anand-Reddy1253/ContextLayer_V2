"""Enums shared across every domain model.

Mirrors docs/DOMAIN_MODEL.md "Enums" exactly. String enums throughout so
values serialize identically to the Postgres CHECK constraints in
docs/persistence.md and to JSON on the wire (API, MCP).
"""

from __future__ import annotations

from enum import StrEnum


class Layer(StrEnum):
    BUSINESS = "BUSINESS"
    TECHNICAL = "TECHNICAL"
    LOGICAL = "LOGICAL"


class NodeStatus(StrEnum):
    ACTIVE = "ACTIVE"
    DEPRECATED = "DEPRECATED"
    ARCHIVED = "ARCHIVED"


class EdgeType(StrEnum):
    CONTAINS = "CONTAINS"
    BELONGS_TO = "BELONGS_TO"
    OWNED_BY = "OWNED_BY"
    HAS_SERVICE = "HAS_SERVICE"
    IMPLEMENTED_BY = "IMPLEMENTED_BY"
    SPECIFIED_BY = "SPECIFIED_BY"
    IMPLEMENTS = "IMPLEMENTS"
    CHANGES = "CHANGES"
    VERIFIES = "VERIFIES"
    DEPENDS_ON = "DEPENDS_ON"
    MENTIONS = "MENTIONS"
    RELATED_TO = "RELATED_TO"
    # Confluence relationship extraction (docs/CONNECTORS.md) — all five
    # deterministic, vendor-declared or table-parsed, never inferred.
    IN_SPACE = "IN_SPACE"
    AUTHORED_BY = "AUTHORED_BY"
    COMMENTED_ON = "COMMENTED_ON"
    LINKS_TO = "LINKS_TO"
    TRANSCLUDES = "TRANSCLUDES"
    HAS_LABEL = "HAS_LABEL"
    # LLM-inferred document relationships (ADR-011) — never deterministic,
    # always origin=LLM_INFERRED, always state=PROPOSED. A document's
    # relationship to a business service reuses RELATED_TO rather than a
    # new type here — it isn't a decision relationship.
    SUPERSEDES = "SUPERSEDES"
    SUPERSEDED_BY = "SUPERSEDED_BY"
    CAUSED_BY = "CAUSED_BY"
    DECIDES_ON = "DECIDES_ON"


class EdgeOrigin(StrEnum):
    SYNC_STRUCTURAL = "SYNC_STRUCTURAL"
    SYNC_EXTRACTED = "SYNC_EXTRACTED"
    HUMAN = "HUMAN"
    RULE = "RULE"
    # A model's own guess, never a vendor-declared or pattern-matched fact
    # (ADR-011) — always paired with state=PROPOSED, never auto-confirmed,
    # regardless of the model's own reported confidence.
    LLM_INFERRED = "LLM_INFERRED"


class EdgeState(StrEnum):
    ACTIVE = "ACTIVE"
    PROPOSED = "PROPOSED"
    REJECTED = "REJECTED"


class SyncStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class ErrorCategory(StrEnum):
    AUTH = "AUTH"
    RATE_LIMITED = "RATE_LIMITED"
    NOT_FOUND = "NOT_FOUND"
    TRANSIENT = "TRANSIENT"
    PERMANENT = "PERMANENT"
    SCHEMA_DRIFT = "SCHEMA_DRIFT"


class Capability(StrEnum):
    """configs/capabilities.yaml's vocabulary. Kept as a code enum, not just
    config-derived, because domain models (Node.capability, Binding.capability)
    need a concrete type to validate against — see domain/config.py for the
    loader that cross-checks configs/capabilities.yaml stays in sync with
    this list.
    """

    CODE = "CODE"
    DOCUMENTATION = "DOCUMENTATION"
    WORK_MANAGEMENT = "WORK_MANAGEMENT"
    CHANGE_REVIEW = "CHANGE_REVIEW"
    BUILD_RELEASE = "BUILD_RELEASE"
    QUALITY = "QUALITY"
    POLICY = "POLICY"
    COMMUNICATION = "COMMUNICATION"
