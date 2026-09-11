"""catalog/business_tree.py + catalog/context_spaces.py CRUD round trip
(docs/phases/PHASE-08.md), using the real
configs/business-tree/acme.yaml and
configs/context-spaces/talentflow-identity.yaml.
"""

import pytest

from context_fabric.catalog import (
    BusinessRefUnresolved,
    add_binding,
    business_path_to_ltree,
    create_context_space,
    find_context_space_config_by_id,
    get_by_business_path,
    get_context_space,
    list_context_spaces,
    load_business_tree_config,
    load_context_space_config,
    remove_binding,
    seed_business_tree,
    update_binding,
)
from context_fabric.domain.enums import Capability
from context_fabric.persistence.repositories.context_space import ContextSpaceRepository
from context_fabric.persistence.repositories.node import NodeRepository


async def test_seed_business_tree_creates_full_org_tree(db_session):
    node_repo = NodeRepository(db_session)
    tree = load_business_tree_config()
    results = await seed_business_tree(node_repo, tree)

    assert set(results) == {
        "ACME",
        "ACME.Engineering",
        "ACME.Engineering.TalentFlow",
        "ACME.Engineering.TalentFlow.Identity",
        "ACME.Engineering.TalentFlow.Payments",
    }
    identity = results["ACME.Engineering.TalentFlow.Identity"]
    assert identity.kind == "SQUAD"
    assert identity.owners == ["identity-squad-lead@acme.example"]


async def test_seed_business_tree_is_idempotent(db_session):
    node_repo = NodeRepository(db_session)
    tree = load_business_tree_config()
    first = await seed_business_tree(node_repo, tree)
    second = await seed_business_tree(node_repo, tree)

    assert first["ACME"].id == second["ACME"].id
    assert first["ACME.Engineering.TalentFlow.Identity"].id == (
        second["ACME.Engineering.TalentFlow.Identity"].id
    )


async def test_get_by_business_path_resolves_seeded_node(db_session):
    node_repo = NodeRepository(db_session)
    await seed_business_tree(node_repo, load_business_tree_config())

    node = await get_by_business_path(node_repo, "ACME/Engineering/TalentFlow/Identity")
    assert node is not None
    assert node.name == "Identity Squad"


async def test_business_path_to_ltree():
    assert (
        business_path_to_ltree("ACME/Engineering/TalentFlow/Identity")
        == "ACME.Engineering.TalentFlow.Identity"
    )


async def test_create_context_space_from_real_config_matches_file(db_session):
    node_repo = NodeRepository(db_session)
    context_space_repo = ContextSpaceRepository(db_session)

    await seed_business_tree(node_repo, load_business_tree_config())
    config_path = find_context_space_config_by_id("talentflow/identity")
    assert config_path is not None
    config = load_context_space_config(config_path)

    space = await create_context_space(context_space_repo, node_repo, config)

    assert space.id == "talentflow/identity"
    assert space.product == "talentflow"
    assert space.teams == ["identity-squad"]
    assert space.services == ["identity-service", "sso-gateway"]
    assert len(space.bindings) == 4
    assert {b.capability for b in space.bindings} == {
        Capability.CODE,
        Capability.WORK_MANAGEMENT,
        Capability.DOCUMENTATION,
    }

    fetched = await get_context_space(context_space_repo, "talentflow/identity")
    assert fetched is not None
    assert len(fetched.bindings) == 4


async def test_create_context_space_without_seeded_business_tree_raises(db_session):
    node_repo = NodeRepository(db_session)
    context_space_repo = ContextSpaceRepository(db_session)
    config_path = find_context_space_config_by_id("talentflow/identity")
    config = load_context_space_config(config_path)  # type: ignore[arg-type]

    with pytest.raises(BusinessRefUnresolved):
        await create_context_space(context_space_repo, node_repo, config)


async def test_list_context_spaces(db_session):
    node_repo = NodeRepository(db_session)
    context_space_repo = ContextSpaceRepository(db_session)
    await seed_business_tree(node_repo, load_business_tree_config())
    config = load_context_space_config(find_context_space_config_by_id("talentflow/identity"))  # type: ignore[arg-type]
    await create_context_space(context_space_repo, node_repo, config)

    spaces = await list_context_spaces(context_space_repo)
    assert [s.id for s in spaces] == ["talentflow/identity"]


async def test_add_update_remove_binding(db_session):
    node_repo = NodeRepository(db_session)
    context_space_repo = ContextSpaceRepository(db_session)
    await seed_business_tree(node_repo, load_business_tree_config())
    config = load_context_space_config(find_context_space_config_by_id("talentflow/identity"))  # type: ignore[arg-type]
    space = await create_context_space(context_space_repo, node_repo, config)

    new_binding = await add_binding(
        context_space_repo,
        space.id,
        capability=Capability.QUALITY,
        source_system="azure_devops",
        source_instance_id="ado-acme",
        native_container="TalentFlow\\Identity\\QA",
    )
    assert new_binding.capability is Capability.QUALITY

    updated = await update_binding(
        context_space_repo, new_binding.model_copy(update={"native_container": "TalentFlow\\QA2"})
    )
    assert updated.native_container == "TalentFlow\\QA2"

    fetched = await get_context_space(context_space_repo, space.id)
    assert len(fetched.bindings) == 5  # type: ignore[union-attr]

    await remove_binding(context_space_repo, new_binding.id)
    fetched_after_remove = await get_context_space(context_space_repo, space.id)
    assert len(fetched_after_remove.bindings) == 4  # type: ignore[union-attr]
