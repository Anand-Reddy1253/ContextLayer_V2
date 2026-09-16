from context_fabric.domain.enums import (
    Capability,
    EdgeOrigin,
    EdgeState,
    EdgeType,
    ErrorCategory,
    Layer,
    NodeStatus,
    SyncStatus,
)


def test_layer_values():
    assert {m.value for m in Layer} == {"BUSINESS", "TECHNICAL", "LOGICAL"}


def test_edge_type_values_match_spec():
    assert {m.value for m in EdgeType} == {
        "CONTAINS",
        "BELONGS_TO",
        "OWNED_BY",
        "HAS_SERVICE",
        "IMPLEMENTED_BY",
        "SPECIFIED_BY",
        "IMPLEMENTS",
        "CHANGES",
        "VERIFIES",
        "DEPENDS_ON",
        "MENTIONS",
        "RELATED_TO",
        # Confluence relationship extraction (docs/CONNECTORS.md) — all
        # vendor-declared or table-parsed, never inferred.
        "IN_SPACE",
        "AUTHORED_BY",
        "COMMENTED_ON",
        "LINKS_TO",
        "TRANSCLUDES",
        "HAS_LABEL",
        # LLM-inferred document relationships (ADR-011) — always
        # origin=LLM_INFERRED, always state=PROPOSED.
        "SUPERSEDES",
        "SUPERSEDED_BY",
        "CAUSED_BY",
        "DECIDES_ON",
    }


def test_edge_origin_values():
    assert {m.value for m in EdgeOrigin} == {
        "SYNC_STRUCTURAL",
        "SYNC_EXTRACTED",
        "HUMAN",
        "RULE",
        "LLM_INFERRED",
    }


def test_edge_state_values():
    assert {m.value for m in EdgeState} == {"ACTIVE", "PROPOSED", "REJECTED"}


def test_node_status_values():
    assert {m.value for m in NodeStatus} == {"ACTIVE", "DEPRECATED", "ARCHIVED"}


def test_sync_status_values():
    assert {m.value for m in SyncStatus} == {
        "PENDING",
        "RUNNING",
        "SUCCEEDED",
        "FAILED",
    }


def test_error_category_values():
    assert {m.value for m in ErrorCategory} == {
        "AUTH",
        "RATE_LIMITED",
        "NOT_FOUND",
        "TRANSIENT",
        "PERMANENT",
        "SCHEMA_DRIFT",
    }


def test_capability_values_match_config_vocabulary():
    assert {m.value for m in Capability} == {
        "CODE",
        "DOCUMENTATION",
        "WORK_MANAGEMENT",
        "CHANGE_REVIEW",
        "BUILD_RELEASE",
        "QUALITY",
        "POLICY",
        "COMMUNICATION",
    }
