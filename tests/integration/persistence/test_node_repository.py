from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from context_fabric.domain.node import Node
from context_fabric.persistence.repositories.node import NodeRepository
from tests.integration.persistence.factories import make_node, make_technical_node


async def test_create_and_get_round_trips_all_fields(db_session, now):
    repo = NodeRepository(db_session)
    node = make_technical_node(
        now,
        description="Identity service repository",
        owners=["identity-squad-lead@acme.example"],
        acl_ref={"group": "identity-squad"},
        attributes={"default_branch": "main"},
        content_hash="abc123",
        source_version="etag-1",
    )

    created = await repo.create(node)
    assert isinstance(created, Node)  # never an ORM object

    fetched = await repo.get(created.id)
    assert isinstance(fetched, Node)
    assert fetched == created
    assert fetched.description == "Identity service repository"
    assert fetched.owners == ["identity-squad-lead@acme.example"]
    assert fetched.acl_ref == {"group": "identity-squad"}
    assert fetched.attributes == {"default_branch": "main"}
    assert fetched.content_hash == "abc123"
    assert fetched.source_version == "etag-1"


async def test_get_missing_returns_none(db_session):
    repo = NodeRepository(db_session)
    assert await repo.get(uuid4()) is None


async def test_get_by_technical_identity(db_session, now):
    repo = NodeRepository(db_session)
    node = make_technical_node(now)
    created = await repo.create(node)

    found = await repo.get_by_technical_identity(
        "github", "github-acme", "acme-org/identity-service"
    )
    assert found is not None
    assert found.id == created.id


async def test_technical_identity_uniqueness_enforced(db_session, now):
    repo = NodeRepository(db_session)
    await repo.create(make_technical_node(now))

    with pytest.raises(IntegrityError):
        await repo.create(make_technical_node(now))


async def test_two_business_nodes_with_null_source_identity_are_not_unique_violation(
    db_session, now
):
    # ux_node_technical_identity only applies WHERE layer = 'TECHNICAL' —
    # two BUSINESS nodes (source_system/native_id both NULL) must not
    # collide, since NULL <> NULL in a unique index.
    repo = NodeRepository(db_session)
    a = await repo.create(make_node(now, path="acme.a"))
    b = await repo.create(make_node(now, path="acme.b"))
    assert a.id != b.id


async def test_soft_delete_sets_deleted_at(db_session, now):
    repo = NodeRepository(db_session)
    node = await repo.create(make_technical_node(now))
    assert node.deleted_at is None

    deleted_at = datetime.now(UTC)
    await repo.soft_delete(node.id, deleted_at)

    fetched = await repo.get(node.id)
    assert fetched is not None
    assert fetched.deleted_at is not None
