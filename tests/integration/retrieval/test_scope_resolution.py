"""docs/phases/PHASE-09.md's exit gate — resolve_scope against real
synced+reconciled graph state (db_session), not mocked data.

native_id values here are deliberately large/distinctive (9010000+) and
source_instance_id is "*-phase9-test" — this shared dev database also
holds real data from live-connector smoke testing (source_instance_id
"ado-acme" et al, native_ids in the low hundreds), which
get_by_technical_identity_any_instance would otherwise match ahead of —
or collide on unique-constraint with — this test's own nodes.
"""

from __future__ import annotations

from uuid import UUID

from context_fabric.domain.context_space import Binding, ContextSpace
from context_fabric.domain.enums import Capability
from context_fabric.persistence.repositories.context_space import ContextSpaceRepository
from context_fabric.persistence.repositories.node import NodeRepository
from context_fabric.retrieval.scope import resolve_scope
from tests.integration.persistence.factories import make_node, make_technical_node

_ADO_INSTANCE = "ado-phase9-test"
_GITHUB_INSTANCE = "github-phase9-test"


async def _seed_worked_example(node_repo, context_space_repo, now):  # type: ignore[no-untyped-def]
    business_node = await node_repo.create(
        make_node(
            now,
            kind="SQUAD",
            name="Identity Squad",
            path="acme.engineering.talentflow.identity",
        )
    )

    await node_repo.create(
        make_technical_node(
            now,
            kind="PROJECT",
            name="TalentFlow",
            path="talentflow",
            source_system="azure_devops",
            source_instance_id=_ADO_INSTANCE,
            native_id="TalentFlowP9Test",
        )
    )
    await node_repo.create(
        make_technical_node(
            now,
            kind="AREA_PATH",
            name="Identity",
            path="talentflow.identity",
            source_system="azure_devops",
            source_instance_id=_ADO_INSTANCE,
            native_id="TalentFlowP9Test\\Identity",
        )
    )
    await node_repo.create(
        make_technical_node(
            now,
            kind="STORY",
            name="Add SSO callback handling",
            path="talentflow.identity.story",
            source_system="azure_devops",
            source_instance_id=_ADO_INSTANCE,
            native_id="9010312",
        )
    )
    await node_repo.create(
        make_technical_node(
            now,
            kind="ORGANIZATION",
            name="acme-org-p9test",
            path="acme_org",
            source_system="github",
            source_instance_id=_GITHUB_INSTANCE,
            native_id="acme-org-p9test",
        )
    )
    await node_repo.create(
        make_technical_node(
            now,
            kind="REPOSITORY",
            name="identity-service",
            path="acme_org.identity_service",
            source_system="github",
            source_instance_id=_GITHUB_INSTANCE,
            native_id="acme-org-p9test/identity-service",
        )
    )
    await node_repo.create(
        make_technical_node(
            now,
            kind="REPOSITORY",
            name="sso-gateway",
            path="acme_org.sso_gateway",
            source_system="github",
            source_instance_id=_GITHUB_INSTANCE,
            native_id="acme-org-p9test/sso-gateway",
        )
    )

    space = ContextSpace(
        id="talentflow/identity-p9test",
        name="TalentFlow — Identity Squad",
        description="",
        product="talentflow",
        teams=["identity-squad"],
        services=["identity-service", "sso-gateway"],
        created_at=now,
        updated_at=now,
        business_node_id=business_node.id,
        bindings=[
            Binding(
                context_space_id="talentflow/identity-p9test",
                capability=Capability.CODE,
                source_system="github",
                source_instance_id=_GITHUB_INSTANCE,
                native_container="acme-org-p9test/identity-service",
                created_at=now,
                updated_at=now,
            ),
            Binding(
                context_space_id="talentflow/identity-p9test",
                capability=Capability.CODE,
                source_system="github",
                source_instance_id=_GITHUB_INSTANCE,
                native_container="acme-org-p9test/sso-gateway",
                created_at=now,
                updated_at=now,
            ),
            Binding(
                context_space_id="talentflow/identity-p9test",
                capability=Capability.WORK_MANAGEMENT,
                source_system="azure_devops",
                source_instance_id=_ADO_INSTANCE,
                native_container="TalentFlowP9Test\\Identity",
                created_at=now,
                updated_at=now,
            ),
        ],
    )
    await context_space_repo.create(space)


async def test_resolve_scope_worked_example(db_session, now):
    node_repo = NodeRepository(db_session)
    context_space_repo = ContextSpaceRepository(db_session)
    await _seed_worked_example(node_repo, context_space_repo, now)

    result = await resolve_scope(node_repo, context_space_repo, "AB#9010312", actor_id="test-actor")

    assert result.resolved is True
    assert result.context_space_id == "talentflow/identity-p9test"
    assert result.product == "talentflow"
    assert result.teams == ["identity-squad"]
    assert result.services == ["identity-service", "sso-gateway"]
    assert set(result.repositories) == {
        "acme-org-p9test/identity-service",
        "acme-org-p9test/sso-gateway",
    }
    assert len(result.candidates) == 1
    assert result.candidates[0].context_space_id == "talentflow/identity-p9test"


async def test_resolve_scope_unrecognized_task_ref_pattern(db_session):
    node_repo = NodeRepository(db_session)
    context_space_repo = ContextSpaceRepository(db_session)

    result = await resolve_scope(node_repo, context_space_repo, "JIRA-123", actor_id="test-actor")

    assert result.resolved is False
    assert "matches no known pattern" in (result.reason or "")
    assert result.candidates == []


async def test_resolve_scope_task_ref_never_synced(db_session):
    node_repo = NodeRepository(db_session)
    context_space_repo = ContextSpaceRepository(db_session)

    result = await resolve_scope(
        node_repo, context_space_repo, "AB#9019999999", actor_id="test-actor"
    )

    assert result.resolved is False
    assert "no synced technical node" in (result.reason or "")


async def test_resolve_scope_no_covering_binding(db_session, now):
    node_repo = NodeRepository(db_session)
    context_space_repo = ContextSpaceRepository(db_session)

    await node_repo.create(
        make_technical_node(
            now,
            kind="STORY",
            name="Orphan story",
            path="orphanprojectp9test.story",
            source_system="azure_devops",
            source_instance_id=_ADO_INSTANCE,
            native_id="9010500",
        )
    )

    result = await resolve_scope(node_repo, context_space_repo, "AB#9010500", actor_id="test-actor")

    assert result.resolved is False
    assert "no context space binding" in (result.reason or "")
    assert result.node_id is not None  # the node itself was found, just unclaimed


async def _seed_business_node(node_repo, now, name: str):  # type: ignore[no-untyped-def]
    return await node_repo.create(
        make_node(now, kind="SQUAD", name=name, path=f"acme.p9test.{name.lower()}")
    )


async def test_resolve_scope_ambiguity_longest_path_wins_over_priority(db_session, now):
    """A broad (project-level) binding with a very high priority must
    still lose to a narrower (area-path-level) binding with priority 0 —
    path specificity is tier 1, priority is only tier 2."""
    node_repo = NodeRepository(db_session)
    context_space_repo = ContextSpaceRepository(db_session)

    await node_repo.create(
        make_technical_node(
            now,
            kind="PROJECT",
            name="WidgetsP9Test",
            path="widgetsp9test",
            source_system="azure_devops",
            source_instance_id=_ADO_INSTANCE,
            native_id="WidgetsP9Test",
        )
    )
    await node_repo.create(
        make_technical_node(
            now,
            kind="AREA_PATH",
            name="Core",
            path="widgetsp9test.core",
            source_system="azure_devops",
            source_instance_id=_ADO_INSTANCE,
            native_id="WidgetsP9Test\\Core",
        )
    )
    await node_repo.create(
        make_technical_node(
            now,
            kind="TASK",
            name="Fix widget rendering",
            path="widgetsp9test.core.task",
            source_system="azure_devops",
            source_instance_id=_ADO_INSTANCE,
            native_id="9010400",
        )
    )

    broad_business = await _seed_business_node(node_repo, now, "Broad")
    narrow_business = await _seed_business_node(node_repo, now, "Narrow")

    await context_space_repo.create(
        ContextSpace(
            id="widgetsp9test/broad",
            name="Widgets (whole project)",
            description="",
            created_at=now,
            updated_at=now,
            business_node_id=broad_business.id,
            bindings=[
                Binding(
                    context_space_id="widgetsp9test/broad",
                    capability=Capability.WORK_MANAGEMENT,
                    source_system="azure_devops",
                    source_instance_id=_ADO_INSTANCE,
                    native_container="WidgetsP9Test",
                    priority=100,
                    created_at=now,
                    updated_at=now,
                ),
            ],
        )
    )
    await context_space_repo.create(
        ContextSpace(
            id="widgetsp9test/core",
            name="Widgets Core Squad",
            description="",
            created_at=now,
            updated_at=now,
            business_node_id=narrow_business.id,
            bindings=[
                Binding(
                    context_space_id="widgetsp9test/core",
                    capability=Capability.WORK_MANAGEMENT,
                    source_system="azure_devops",
                    source_instance_id=_ADO_INSTANCE,
                    native_container="WidgetsP9Test\\Core",
                    priority=0,
                    created_at=now,
                    updated_at=now,
                ),
            ],
        )
    )

    result = await resolve_scope(node_repo, context_space_repo, "AB#9010400", actor_id="test-actor")

    assert result.resolved is True
    assert result.context_space_id == "widgetsp9test/core"
    assert {c.context_space_id for c in result.candidates} == {
        "widgetsp9test/broad",
        "widgetsp9test/core",
    }

    # context_space_override restricts the search up front — the broad
    # space wins here purely because it's the only one considered, not
    # because it out-competed the narrower one on the tiebreak.
    overridden = await resolve_scope(
        node_repo,
        context_space_repo,
        "AB#9010400",
        actor_id="test-actor",
        context_space_override="widgetsp9test/broad",
    )
    assert overridden.resolved is True
    assert overridden.context_space_id == "widgetsp9test/broad"
    assert len(overridden.candidates) == 1


async def test_resolve_scope_ambiguity_priority_breaks_equal_depth_tie(db_session, now):
    """Two bindings pointing at the exact same node (identical match
    depth) — the higher-priority one must win."""
    node_repo = NodeRepository(db_session)
    context_space_repo = ContextSpaceRepository(db_session)

    await node_repo.create(
        make_technical_node(
            now,
            kind="AREA_PATH",
            name="Shared",
            path="sharedprojectp9test.shared",
            source_system="azure_devops",
            source_instance_id=_ADO_INSTANCE,
            native_id="SharedP9Test\\Area",
        )
    )
    await node_repo.create(
        make_technical_node(
            now,
            kind="TASK",
            name="Shared task",
            path="sharedprojectp9test.shared.task",
            source_system="azure_devops",
            source_instance_id=_ADO_INSTANCE,
            native_id="9010401",
        )
    )

    low_business = await _seed_business_node(node_repo, now, "Lowprio")
    high_business = await _seed_business_node(node_repo, now, "Highprio")

    await context_space_repo.create(
        ContextSpace(
            id="sharedp9test/low",
            name="Low priority claimant",
            description="",
            created_at=now,
            updated_at=now,
            business_node_id=low_business.id,
            bindings=[
                Binding(
                    context_space_id="sharedp9test/low",
                    capability=Capability.WORK_MANAGEMENT,
                    source_system="azure_devops",
                    source_instance_id=_ADO_INSTANCE,
                    native_container="SharedP9Test\\Area",
                    priority=0,
                    created_at=now,
                    updated_at=now,
                ),
            ],
        )
    )
    await context_space_repo.create(
        ContextSpace(
            id="sharedp9test/high",
            name="High priority claimant",
            description="",
            created_at=now,
            updated_at=now,
            business_node_id=high_business.id,
            bindings=[
                Binding(
                    context_space_id="sharedp9test/high",
                    capability=Capability.WORK_MANAGEMENT,
                    source_system="azure_devops",
                    source_instance_id=_ADO_INSTANCE,
                    native_container="SharedP9Test\\Area",
                    priority=9,
                    created_at=now,
                    updated_at=now,
                ),
            ],
        )
    )

    result = await resolve_scope(node_repo, context_space_repo, "AB#9010401", actor_id="test-actor")

    assert result.resolved is True
    assert result.context_space_id == "sharedp9test/high"
    assert len(result.candidates) == 2


async def test_resolve_scope_ambiguity_binding_id_breaks_final_tie(db_session, now):
    """Equal depth, equal priority — the lowest binding id wins, purely
    for deterministic stability, not because it means anything."""
    node_repo = NodeRepository(db_session)
    context_space_repo = ContextSpaceRepository(db_session)

    await node_repo.create(
        make_technical_node(
            now,
            kind="AREA_PATH",
            name="Tied",
            path="tiedprojectp9test.tied",
            source_system="azure_devops",
            source_instance_id=_ADO_INSTANCE,
            native_id="TiedP9Test\\Area",
        )
    )
    await node_repo.create(
        make_technical_node(
            now,
            kind="TASK",
            name="Tied task",
            path="tiedprojectp9test.tied.task",
            source_system="azure_devops",
            source_instance_id=_ADO_INSTANCE,
            native_id="9010402",
        )
    )

    business_a = await _seed_business_node(node_repo, now, "Tieda")
    business_b = await _seed_business_node(node_repo, now, "Tiedb")

    low_id = UUID(int=1)
    high_id = UUID(int=2)

    await context_space_repo.create(
        ContextSpace(
            id="tiedp9test/high-id",
            name="Higher UUID claimant",
            description="",
            created_at=now,
            updated_at=now,
            business_node_id=business_a.id,
            bindings=[
                Binding(
                    id=high_id,
                    context_space_id="tiedp9test/high-id",
                    capability=Capability.WORK_MANAGEMENT,
                    source_system="azure_devops",
                    source_instance_id=_ADO_INSTANCE,
                    native_container="TiedP9Test\\Area",
                    priority=0,
                    created_at=now,
                    updated_at=now,
                ),
            ],
        )
    )
    await context_space_repo.create(
        ContextSpace(
            id="tiedp9test/low-id",
            name="Lower UUID claimant",
            description="",
            created_at=now,
            updated_at=now,
            business_node_id=business_b.id,
            bindings=[
                Binding(
                    id=low_id,
                    context_space_id="tiedp9test/low-id",
                    capability=Capability.WORK_MANAGEMENT,
                    source_system="azure_devops",
                    source_instance_id=_ADO_INSTANCE,
                    native_container="TiedP9Test\\Area",
                    priority=0,
                    created_at=now,
                    updated_at=now,
                ),
            ],
        )
    )

    result = await resolve_scope(node_repo, context_space_repo, "AB#9010402", actor_id="test-actor")

    assert result.resolved is True
    assert result.context_space_id == "tiedp9test/low-id"
    assert result.candidates[0].binding.id == low_id
