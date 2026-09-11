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


class EdgeOrigin(StrEnum):
    SYNC_STRUCTURAL = "SYNC_STRUCTURAL"
    SYNC_EXTRACTED = "SYNC_EXTRACTED"
    HUMAN = "HUMAN"
    RULE = "RULE"


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
