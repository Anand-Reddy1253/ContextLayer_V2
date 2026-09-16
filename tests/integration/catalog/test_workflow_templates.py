"""catalog/workflow_templates.py CRUD round trip — same shape as
test_context_spaces.py's coverage of catalog/context_spaces.py."""

from __future__ import annotations

import pytest

from context_fabric.catalog import (
    AiAssetNotFound,
    NotAnAiAsset,
    add_step,
    create_context_space_from_fields,
    create_workflow_template,
    delete_workflow_template,
    get_workflow_template,
    list_workflow_templates,
    remove_step,
    reorder_steps,
)
from context_fabric.persistence.repositories.context_space import ContextSpaceRepository
from context_fabric.persistence.repositories.node import NodeRepository
from context_fabric.persistence.repositories.workflow_template import WorkflowTemplateRepository
from tests.integration.persistence.factories import make_node, make_technical_node

_INSTANCE = "github-wf-test"


async def _seed_context_space_with_repo(node_repo, context_space_repo, now):  # type: ignore[no-untyped-def]
    business_node = await node_repo.create(
        make_node(now, kind="SQUAD", name="Identity Squad", path="acme.identity.wftest")
    )
    space = await create_context_space_from_fields(
        context_space_repo,
        id="talentflow/identity-wftest",
        name="TalentFlow — Identity",
        description="",
        business_node_id=business_node.id,
    )
    return space


async def _seed_ai_asset(node_repo, now, *, native_id: str = "acme-org/identity-service#agent-reviewer.md"):  # type: ignore[no-untyped-def]
    return await node_repo.create(
        make_technical_node(
            now,
            kind="AI_ASSET",
            name="Reviewer",
            path="github_wftest.acme_org.identity_service.agents.reviewer",
            source_system="github",
            source_instance_id=_INSTANCE,
            native_id=native_id,
            attributes={"vendor": "github", "asset_type": "agent", "path": ".github/agents/reviewer.md"},
        )
    )


async def test_create_workflow_template_round_trip(db_session, now):
    node_repo = NodeRepository(db_session)
    context_space_repo = ContextSpaceRepository(db_session)
    template_repo = WorkflowTemplateRepository(db_session)

    space = await _seed_context_space_with_repo(node_repo, context_space_repo, now)

    template = await create_workflow_template(
        template_repo,
        context_space_id=space.id,
        name="PR review",
        description="Run the reviewer agent on every PR.",
    )

    assert template.name == "PR review"
    assert template.context_space_id == space.id
    assert template.steps == []

    fetched = await get_workflow_template(template_repo, template.id)
    assert fetched is not None
    assert fetched.id == template.id


async def test_list_workflow_templates_filters_by_context_space(db_session, now):
    node_repo = NodeRepository(db_session)
    context_space_repo = ContextSpaceRepository(db_session)
    template_repo = WorkflowTemplateRepository(db_session)

    space = await _seed_context_space_with_repo(node_repo, context_space_repo, now)
    await create_workflow_template(template_repo, context_space_id=space.id, name="A")
    await create_workflow_template(template_repo, context_space_id=space.id, name="B")

    all_templates = await list_workflow_templates(template_repo)
    scoped = await list_workflow_templates(template_repo, context_space_id=space.id)
    empty = await list_workflow_templates(template_repo, context_space_id="nonexistent/space")

    assert {t.name for t in scoped} == {"A", "B"}
    assert len(all_templates) >= len(scoped)
    assert empty == []


async def test_add_step_snapshots_ai_asset_fields_and_orders_sequentially(db_session, now):
    node_repo = NodeRepository(db_session)
    context_space_repo = ContextSpaceRepository(db_session)
    template_repo = WorkflowTemplateRepository(db_session)

    space = await _seed_context_space_with_repo(node_repo, context_space_repo, now)
    template = await create_workflow_template(template_repo, context_space_id=space.id, name="PR review")

    reviewer = await _seed_ai_asset(node_repo, now, native_id="acme-org/identity-service#reviewer")
    tester = await _seed_ai_asset(node_repo, now, native_id="acme-org/identity-service#tester")

    step1 = await add_step(
        template_repo,
        node_repo,
        template.id,
        source_system="github",
        source_instance_id=_INSTANCE,
        native_id=reviewer.native_id,
    )
    step2 = await add_step(
        template_repo,
        node_repo,
        template.id,
        source_system="github",
        source_instance_id=_INSTANCE,
        native_id=tester.native_id,
        instructions="Run after review passes.",
    )

    assert step1.order == 0
    assert step2.order == 1
    assert step1.label == "Reviewer"
    assert step1.vendor == "github"
    assert step1.asset_type == "agent"
    assert step2.instructions == "Run after review passes."

    fetched = await get_workflow_template(template_repo, template.id)
    assert fetched is not None
    assert [s.native_id for s in fetched.steps] == [reviewer.native_id, tester.native_id]


async def test_add_step_rejects_unsynced_native_id(db_session, now):
    node_repo = NodeRepository(db_session)
    context_space_repo = ContextSpaceRepository(db_session)
    template_repo = WorkflowTemplateRepository(db_session)

    space = await _seed_context_space_with_repo(node_repo, context_space_repo, now)
    template = await create_workflow_template(template_repo, context_space_id=space.id, name="PR review")

    with pytest.raises(AiAssetNotFound):
        await add_step(
            template_repo,
            node_repo,
            template.id,
            source_system="github",
            source_instance_id=_INSTANCE,
            native_id="acme-org/identity-service#never-synced",
        )


async def test_add_step_rejects_non_ai_asset_node(db_session, now):
    node_repo = NodeRepository(db_session)
    context_space_repo = ContextSpaceRepository(db_session)
    template_repo = WorkflowTemplateRepository(db_session)

    space = await _seed_context_space_with_repo(node_repo, context_space_repo, now)
    template = await create_workflow_template(template_repo, context_space_id=space.id, name="PR review")

    repo_node = await node_repo.create(
        make_technical_node(
            now,
            kind="REPOSITORY",
            name="identity-service",
            path="github_wftest2.acme_org.identity_service",
            source_system="github",
            source_instance_id=_INSTANCE,
            native_id="acme-org/identity-service-repo-not-asset",
        )
    )

    with pytest.raises(NotAnAiAsset):
        await add_step(
            template_repo,
            node_repo,
            template.id,
            source_system="github",
            source_instance_id=_INSTANCE,
            native_id=repo_node.native_id,
        )


async def test_remove_step(db_session, now):
    node_repo = NodeRepository(db_session)
    context_space_repo = ContextSpaceRepository(db_session)
    template_repo = WorkflowTemplateRepository(db_session)

    space = await _seed_context_space_with_repo(node_repo, context_space_repo, now)
    template = await create_workflow_template(template_repo, context_space_id=space.id, name="PR review")
    reviewer = await _seed_ai_asset(node_repo, now, native_id="acme-org/identity-service#rm-target")
    step = await add_step(
        template_repo,
        node_repo,
        template.id,
        source_system="github",
        source_instance_id=_INSTANCE,
        native_id=reviewer.native_id,
    )

    await remove_step(template_repo, step.id)

    fetched = await get_workflow_template(template_repo, template.id)
    assert fetched is not None
    assert fetched.steps == []


async def test_reorder_steps(db_session, now):
    node_repo = NodeRepository(db_session)
    context_space_repo = ContextSpaceRepository(db_session)
    template_repo = WorkflowTemplateRepository(db_session)

    space = await _seed_context_space_with_repo(node_repo, context_space_repo, now)
    template = await create_workflow_template(template_repo, context_space_id=space.id, name="PR review")

    first = await _seed_ai_asset(node_repo, now, native_id="acme-org/identity-service#first")
    second = await _seed_ai_asset(node_repo, now, native_id="acme-org/identity-service#second")

    step_a = await add_step(
        template_repo, node_repo, template.id,
        source_system="github", source_instance_id=_INSTANCE, native_id=first.native_id,
    )
    step_b = await add_step(
        template_repo, node_repo, template.id,
        source_system="github", source_instance_id=_INSTANCE, native_id=second.native_id,
    )

    reordered = await reorder_steps(template_repo, template.id, [step_b.id, step_a.id])
    assert [s.id for s in reordered] == [step_b.id, step_a.id]
    assert reordered[0].order == 0
    assert reordered[1].order == 1

    fetched = await get_workflow_template(template_repo, template.id)
    assert fetched is not None
    assert [s.id for s in fetched.steps] == [step_b.id, step_a.id]


async def test_reorder_steps_rejects_mismatched_id_set(db_session, now):
    node_repo = NodeRepository(db_session)
    context_space_repo = ContextSpaceRepository(db_session)
    template_repo = WorkflowTemplateRepository(db_session)

    space = await _seed_context_space_with_repo(node_repo, context_space_repo, now)
    template = await create_workflow_template(template_repo, context_space_id=space.id, name="PR review")
    reviewer = await _seed_ai_asset(node_repo, now, native_id="acme-org/identity-service#mismatch")
    step = await add_step(
        template_repo, node_repo, template.id,
        source_system="github", source_instance_id=_INSTANCE, native_id=reviewer.native_id,
    )

    with pytest.raises(ValueError):
        await reorder_steps(template_repo, template.id, [step.id, step.id])


async def test_delete_workflow_template_cascades_steps(db_session, now):
    node_repo = NodeRepository(db_session)
    context_space_repo = ContextSpaceRepository(db_session)
    template_repo = WorkflowTemplateRepository(db_session)

    space = await _seed_context_space_with_repo(node_repo, context_space_repo, now)
    template = await create_workflow_template(template_repo, context_space_id=space.id, name="PR review")
    reviewer = await _seed_ai_asset(node_repo, now, native_id="acme-org/identity-service#cascade")
    await add_step(
        template_repo, node_repo, template.id,
        source_system="github", source_instance_id=_INSTANCE, native_id=reviewer.native_id,
    )

    await delete_workflow_template(template_repo, template.id)

    assert await get_workflow_template(template_repo, template.id) is None
