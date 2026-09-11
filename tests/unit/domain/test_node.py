import pytest
from pydantic import ValidationError

from context_fabric.domain.enums import Layer, NodeStatus
from context_fabric.domain.node import Node


def _base_kwargs(now, **overrides):
    kwargs = dict(
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
    return kwargs


def test_business_node_constructs(now):
    node = Node(**_base_kwargs(now))
    assert node.layer is Layer.BUSINESS
    assert node.status is NodeStatus.ACTIVE
    assert node.source_system is None
    assert node.native_id is None


def test_technical_node_requires_source_identity(now):
    node = Node(
        **_base_kwargs(
            now,
            layer=Layer.TECHNICAL,
            kind="REPOSITORY",
            source_system="github",
            source_instance_id="github-acme",
            native_id="acme-org/identity-service",
        )
    )
    assert node.source_system == "github"
    assert node.native_id == "acme-org/identity-service"


def test_technical_node_without_source_system_rejected(now):
    with pytest.raises(ValidationError, match="TECHNICAL nodes require"):
        Node(**_base_kwargs(now, layer=Layer.TECHNICAL, kind="REPOSITORY"))


def test_technical_node_without_native_id_rejected(now):
    with pytest.raises(ValidationError, match="TECHNICAL nodes require"):
        Node(
            **_base_kwargs(
                now,
                layer=Layer.TECHNICAL,
                kind="REPOSITORY",
                source_system="github",
            )
        )


def test_business_node_with_source_system_rejected(now):
    with pytest.raises(ValidationError, match="must not set source_system"):
        Node(**_base_kwargs(now, source_system="github"))


def test_logical_node_with_native_id_rejected(now):
    with pytest.raises(ValidationError, match="must not set source_system"):
        Node(
            **_base_kwargs(
                now, layer=Layer.LOGICAL, kind="CONTEXT_SPACE", native_id="x"
            )
        )


def test_invalid_ltree_path_rejected(now):
    with pytest.raises(ValidationError, match="invalid ltree label"):
        Node(**_base_kwargs(now, path="acme..bad path"))
