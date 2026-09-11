"""Shared domain-object builders for persistence integration tests."""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from context_fabric.domain.edge import Edge
from context_fabric.domain.enums import EdgeOrigin, EdgeType, Layer
from context_fabric.domain.evidence import Evidence
from context_fabric.domain.node import Node


def make_node(now: datetime, **overrides: object) -> Node:
    kwargs: dict[str, object] = dict(
        layer=Layer.BUSINESS,
        kind="TEAM",
        name="Identity Squad",
        path="acme.engineering.talentflow.identity",
        first_seen_at=now,
        last_seen_at=now,
        created_at=now,
        updated_at=now,
    )
    kwargs.update(overrides)
    return Node(**kwargs)  # type: ignore[arg-type]


def make_technical_node(now: datetime, **overrides: object) -> Node:
    kwargs: dict[str, object] = dict(
        layer=Layer.TECHNICAL,
        kind="REPOSITORY",
        name="identity-service",
        path="github.acme_org.identity_service",
        source_system="github",
        source_instance_id="github-acme",
        native_id="acme-org/identity-service",
        first_seen_at=now,
        last_seen_at=now,
        created_at=now,
        updated_at=now,
    )
    kwargs.update(overrides)
    return Node(**kwargs)  # type: ignore[arg-type]


def make_edge(now: datetime, src_id, dst_id, **overrides: object) -> Edge:  # type: ignore[no-untyped-def]
    kwargs: dict[str, object] = dict(
        src_id=src_id,
        dst_id=dst_id,
        type=EdgeType.CONTAINS,
        origin=EdgeOrigin.SYNC_STRUCTURAL,
        first_seen_at=now,
        last_seen_at=now,
    )
    kwargs.update(overrides)
    return Edge(**kwargs)  # type: ignore[arg-type]


def make_evidence(now: datetime, node_id, **overrides: object) -> Evidence:  # type: ignore[no-untyped-def]
    kwargs: dict[str, object] = dict(
        node_id=node_id,
        source_system="azure_devops",
        source_instance_id="ado-acme",
        native_id=str(uuid4()),
        uri="https://dev.azure.com/acme/_workitems/edit/312",
        retrieved_at=now,
    )
    kwargs.update(overrides)
    return Evidence(**kwargs)  # type: ignore[arg-type]
