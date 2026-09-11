from context_fabric.domain.context_space import Binding, ContextSpace
from context_fabric.domain.enums import Capability
from context_fabric.persistence.repositories.context_space import ContextSpaceRepository
from context_fabric.persistence.repositories.node import NodeRepository
from tests.integration.persistence.factories import make_node


async def test_create_with_bindings_round_trips(db_session, now):
    node_repo = NodeRepository(db_session)
    space_repo = ContextSpaceRepository(db_session)
    business_node = await node_repo.create(make_node(now, kind="SQUAD"))

    space = ContextSpace(
        id="talentflow/identity",
        name="TalentFlow — Identity Squad",
        description="Identity and access management capability.",
        owners=["identity-squad-lead@acme.example"],
        product="talentflow",
        teams=["identity-squad"],
        services=["identity-service", "sso-gateway"],
        created_at=now,
        updated_at=now,
        business_node_id=business_node.id,
        bindings=[
            Binding(
                context_space_id="talentflow/identity",
                capability=Capability.CODE,
                source_system="github",
                source_instance_id="github-acme",
                native_container="acme-org/identity-service",
                created_at=now,
                updated_at=now,
            ),
            Binding(
                context_space_id="talentflow/identity",
                capability=Capability.WORK_MANAGEMENT,
                source_system="azure_devops",
                source_instance_id="ado-acme",
                native_container="TalentFlow\\Identity",
                created_at=now,
                updated_at=now,
            ),
        ],
    )

    created = await space_repo.create(space)
    assert created.id == "talentflow/identity"
    assert len(created.bindings) == 2

    fetched = await space_repo.get("talentflow/identity")
    assert fetched is not None
    assert {b.capability for b in fetched.bindings} == {
        Capability.CODE,
        Capability.WORK_MANAGEMENT,
    }
    assert fetched.services == ["identity-service", "sso-gateway"]


async def test_add_binding_to_existing_space(db_session, now):
    node_repo = NodeRepository(db_session)
    space_repo = ContextSpaceRepository(db_session)
    business_node = await node_repo.create(make_node(now, kind="SQUAD"))

    space = ContextSpace(
        id="talentflow/identity",
        name="Identity Squad",
        description="",
        created_at=now,
        updated_at=now,
        business_node_id=business_node.id,
    )
    await space_repo.create(space)

    binding = Binding(
        context_space_id="talentflow/identity",
        capability=Capability.DOCUMENTATION,
        source_system="confluence",
        source_instance_id="confluence-acme",
        native_container="PLATFORM/Identity",
        created_at=now,
        updated_at=now,
    )
    added = await space_repo.add_binding(binding)
    assert added.capability is Capability.DOCUMENTATION

    fetched = await space_repo.get("talentflow/identity")
    assert len(fetched.bindings) == 1


async def test_get_missing_returns_none(db_session):
    space_repo = ContextSpaceRepository(db_session)
    assert await space_repo.get("does/not-exist") is None


async def test_binding_priority_round_trips_through_create_and_update(db_session, now):
    """Binding.priority (docs/RETRIEVAL.md §1's ambiguity tiebreak) was
    silently dropped end-to-end: create/add_binding/update_binding never
    read or wrote the column, so every binding always came back with the
    model default (0) regardless of what was actually stored. A resolver
    reading priority=0 for everything would make the tiebreak inert
    without ever failing loudly."""
    node_repo = NodeRepository(db_session)
    space_repo = ContextSpaceRepository(db_session)
    business_node = await node_repo.create(make_node(now, kind="SQUAD"))

    space = ContextSpace(
        id="talentflow/identity",
        name="Identity Squad",
        description="",
        created_at=now,
        updated_at=now,
        business_node_id=business_node.id,
        bindings=[
            Binding(
                context_space_id="talentflow/identity",
                capability=Capability.CODE,
                source_system="github",
                source_instance_id="github-acme",
                native_container="acme-org/identity-service",
                priority=5,
                created_at=now,
                updated_at=now,
            ),
        ],
    )
    created = await space_repo.create(space)
    assert created.bindings[0].priority == 5

    fetched = await space_repo.get("talentflow/identity")
    assert fetched is not None
    assert fetched.bindings[0].priority == 5

    updated = await space_repo.update_binding(
        fetched.bindings[0].model_copy(update={"priority": 9})
    )
    assert updated.priority == 9
    refetched = await space_repo.get("talentflow/identity")
    assert refetched is not None
    assert refetched.bindings[0].priority == 9
