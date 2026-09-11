import pytest

from context_fabric.connectors.jira.fixture import JiraFixtureConnector
from context_fabric.domain.errors import NotFound


@pytest.fixture
def connector() -> JiraFixtureConnector:
    return JiraFixtureConnector()


async def test_discover_containers_returns_projects(connector: JiraFixtureConnector) -> None:
    containers = await connector.discover_containers()
    assert {c.native_id for c in containers} == {"TALENT", "PLAT"}
    assert all(c.kind == "PROJECT" for c in containers)


async def test_list_children_walks_project_to_issue_to_leaves(
    connector: JiraFixtureConnector,
) -> None:
    project_children = await connector.list_children("TALENT")
    assert [c.native_id for c in project_children.items] == ["TALENT-1"]

    epic_children = await connector.list_children("TALENT-1")
    assert {c.native_id for c in epic_children.items} == {"TALENT-2", "TALENT-3"}

    story_children = await connector.list_children("TALENT-2")
    kinds = {c.kind for c in story_children.items}
    assert kinds == {"SUBTASK", "COMMENT"}


async def test_get_object_resolves_issue_and_comment(connector: JiraFixtureConnector) -> None:
    issue = await connector.get_object("TALENT-1")
    assert issue.kind == "EPIC"

    subtask = await connector.get_object("TALENT-4")
    assert subtask.kind == "SUBTASK"

    comment = await connector.get_object("COMMENT-9001")
    assert comment.kind == "COMMENT"

    with pytest.raises(NotFound):
        await connector.get_object("does-not-exist")


async def test_get_content_fetches_issue_description_on_demand(
    connector: JiraFixtureConnector,
) -> None:
    content = await connector.get_content("TALENT-1")
    assert "AB#312" in (content.text or "")


async def test_get_links_extracts_structured_and_mentioned_links(
    connector: JiraFixtureConnector,
) -> None:
    links = await connector.get_links("TALENT-1")
    refs = {link.target_ref for link in links}
    assert "AB#312" in refs

    story_links = await connector.get_links("TALENT-2")
    story_refs = {(link.target_ref, link.link_kind) for link in story_links}
    assert ("TALENT-3", "depends_on") in story_refs
    assert ("PR-42", "mentions") in story_refs
    assert ("acme/talentflow-api#7", "mentions") in story_refs


async def test_get_acl_reference(connector: JiraFixtureConnector) -> None:
    ref = await connector.get_acl_reference("TALENT-1")
    assert ref.acl_ref["project"] == "TALENT"


async def test_get_changes_is_always_empty(connector: JiraFixtureConnector) -> None:
    changes = await connector.get_changes()
    assert changes.items == []
    assert changes.has_more is False
