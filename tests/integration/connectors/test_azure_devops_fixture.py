"""End-to-end exercise of AzureDevOpsFixtureConnector against the real
fixture files in fixtures/azure_devops/ (not mocked) — docs/phases/PHASE-04.md.
"""

import pytest

from context_fabric.connectors.azure_devops.fixture import AzureDevOpsFixtureConnector
from context_fabric.domain.errors import NotFound


@pytest.fixture
def connector() -> AzureDevOpsFixtureConnector:
    return AzureDevOpsFixtureConnector()


async def test_discover_containers_returns_the_project(connector):
    containers = await connector.discover_containers()
    assert [c.native_id for c in containers] == ["TalentFlow"]
    assert containers[0].kind == "PROJECT"


async def test_list_children_of_project_returns_area_paths(connector):
    page = await connector.list_children("TalentFlow")
    names = {c.name for c in page.items}
    assert names == {"Identity", "Payments"}
    assert page.next_cursor is None  # exactly 2 items, page size 2


async def test_list_children_walks_area_path_to_epic_to_feature_to_story(connector):
    epics = (await connector.list_children("TalentFlow\\Identity")).items
    assert [e.native_id for e in epics] == ["301"]

    features = (await connector.list_children("301")).items
    assert [f.native_id for f in features] == ["305"]

    # Feature 305 has 4 children (3 stories + 1 bug) with page size 2 —
    # the documented pagination boundary.
    page1 = await connector.list_children("305")
    assert len(page1.items) == 2
    assert page1.next_cursor == "2"

    page2 = await connector.list_children("305", cursor=page1.next_cursor)
    assert len(page2.items) == 2
    assert page2.next_cursor is None

    all_children = {item.native_id for item in [*page1.items, *page2.items]}
    assert all_children == {"312", "313", "314", "340"}


async def test_get_object_resolves_work_item_pr_build_and_area_path(connector):
    story = await connector.get_object("312")
    assert story.kind == "STORY"

    pr = await connector.get_object("PR-42")
    assert pr.kind == "PULL_REQUEST"

    build = await connector.get_object("BUILD-100")
    assert build.kind == "BUILD"

    area = await connector.get_object("TalentFlow\\Identity")
    assert area.kind == "AREA_PATH"


async def test_get_object_missing_raises_not_found(connector):
    with pytest.raises(NotFound):
        await connector.get_object("does-not-exist")


async def test_get_content_returns_description(connector):
    content = await connector.get_content("312")
    assert "callback" in content.text.lower()


async def test_get_content_missing_raises_not_found(connector):
    with pytest.raises(NotFound):
        await connector.get_content("does-not-exist")


async def test_get_changes_paginates_and_includes_a_tombstone(connector):
    # changes.json has 2 items at a fixture page size of 1 — a genuine
    # 2-page cursor walk, not a single call.
    page1 = await connector.get_changes()
    assert len(page1.items) == 1
    assert page1.has_more is True
    assert page1.next_cursor == "1"

    page2 = await connector.get_changes(cursor=page1.next_cursor)
    assert len(page2.items) == 1
    assert page2.has_more is False
    assert page2.next_cursor is None

    by_id = {item.native_id: item for item in [*page1.items, *page2.items]}
    assert by_id["299"].deleted is True
    assert by_id["340"].deleted is False
    assert by_id["340"].kind == "BUG"


async def test_get_links_resolves_to_pr_and_mention(connector):
    links = await connector.get_links("312")
    targets = {(link.target_ref, link.link_kind) for link in links}
    assert ("PR-42", "relates_to") in targets
    assert ("AB#301", "mentions") in targets

    # Both targets are real objects/refs elsewhere in the fixture data —
    # proves the extraction path Phase 7 needs has something real to
    # resolve against.
    pr = await connector.get_object("PR-42")
    assert pr is not None


async def test_get_links_unknown_native_id_returns_empty(connector):
    assert await connector.get_links("does-not-exist") == []


async def test_get_acl_reference(connector):
    ref = await connector.get_acl_reference("312")
    assert ref.acl_ref["group"] == "identity-squad"


async def test_get_acl_reference_missing_raises_not_found(connector):
    with pytest.raises(NotFound):
        await connector.get_acl_reference("does-not-exist")
