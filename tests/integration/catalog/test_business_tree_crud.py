"""catalog/business_tree.py's create/update CRUD (docs/UI.md "Business
Hierarchy") — create_business_node and delete_business_node were
fast-tracked ahead of Phase 16 with no dedicated test file; this one
covers update_business_node, added alongside the "business context"
attributes (criticality_tier, compliance_scope, stakeholders,
communication_channel).
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from context_fabric.catalog import create_business_node, update_business_node
from context_fabric.domain.enums import Layer
from context_fabric.domain.node import Node
from context_fabric.persistence.repositories.node import NodeRepository


async def test_update_business_node_merges_business_context_attributes(db_session):
    node_repo = NodeRepository(db_session)
    node = await create_business_node(node_repo, parent_id=None, kind="SQUAD", name="Identity")

    updated = await update_business_node(
        node_repo,
        node.id,
        attributes={"criticality_tier": "prod-critical", "compliance_scope": ["PCI", "SOC2"]},
    )

    assert updated.attributes["criticality_tier"] == "prod-critical"
    assert updated.attributes["compliance_scope"] == ["PCI", "SOC2"]

    # A second partial update merges in rather than clobbering — adding
    # stakeholders must not drop criticality_tier/compliance_scope.
    updated_again = await update_business_node(
        node_repo, node.id, attributes={"stakeholders": ["VP Eng: Jane Doe"]}
    )
    assert updated_again.attributes["criticality_tier"] == "prod-critical"
    assert updated_again.attributes["stakeholders"] == ["VP Eng: Jane Doe"]


async def test_update_business_node_clears_attribute_set_to_none(db_session):
    node_repo = NodeRepository(db_session)
    node = await create_business_node(node_repo, parent_id=None, kind="SQUAD", name="Payments")
    await update_business_node(node_repo, node.id, attributes={"criticality_tier": "standard"})

    cleared = await update_business_node(
        node_repo, node.id, attributes={"criticality_tier": None}
    )
    assert "criticality_tier" not in cleared.attributes


async def test_update_business_node_fixes_mislabeled_kind(db_session):
    node_repo = NodeRepository(db_session)
    node = await create_business_node(node_repo, parent_id=None, kind="SQUAD", name="Root")

    fixed = await update_business_node(node_repo, node.id, kind="ORG")
    assert fixed.kind == "ORG"
    assert fixed.name == "Root"  # untouched — omitted, not cleared


async def test_update_business_node_updates_name_and_description_independently(db_session):
    node_repo = NodeRepository(db_session)
    node = await create_business_node(
        node_repo, parent_id=None, kind="TEAM", name="Old Name", description="old desc"
    )

    renamed = await update_business_node(node_repo, node.id, name="New Name")
    assert renamed.name == "New Name"
    assert renamed.description == "old desc"  # untouched — omitted, not cleared


async def test_update_business_node_raises_for_missing_node(db_session):
    node_repo = NodeRepository(db_session)

    with pytest.raises(ValueError, match="not found"):
        await update_business_node(node_repo, uuid4(), name="x")


async def test_update_business_node_rejects_non_business_node(db_session):
    node_repo = NodeRepository(db_session)
    now = datetime.now(UTC)
    technical = await node_repo.create(
        Node(
            layer=Layer.TECHNICAL,
            kind="WORK_ITEM",
            name="Some work item",
            source_system="azure_devops",
            source_instance_id="ado-acme-crud-test",
            native_id="crud-test-1",
            path="ado_acme_crud_test.crud_test_1",
            first_seen_at=now,
            last_seen_at=now,
            created_at=now,
            updated_at=now,
        )
    )

    with pytest.raises(ValueError, match="not a BUSINESS node"):
        await update_business_node(node_repo, technical.id, name="x")
