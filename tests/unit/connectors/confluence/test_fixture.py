import pytest

from context_fabric.connectors.confluence.fixture import ConfluenceFixtureConnector
from context_fabric.domain.errors import NotFound


@pytest.fixture
def connector() -> ConfluenceFixtureConnector:
    return ConfluenceFixtureConnector()


async def test_discover_containers_returns_spaces(connector: ConfluenceFixtureConnector) -> None:
    containers = await connector.discover_containers()
    assert {c.native_id for c in containers} == {"98305", "98306"}
    assert all(c.kind == "SPACE" for c in containers)


async def test_list_children_walks_space_to_page_to_leaves(
    connector: ConfluenceFixtureConnector,
) -> None:
    space_children = await connector.list_children("98305")
    assert [c.native_id for c in space_children.items] == ["131073"]

    page_children = await connector.list_children("131073")
    assert [c.native_id for c in page_children.items] == ["131074"]

    leaf_children = await connector.list_children("131074")
    kinds = {c.kind for c in leaf_children.items}
    assert kinds == {"ATTACHMENT", "COMMENT"}


async def test_get_object_resolves_page_attachment_and_comment(
    connector: ConfluenceFixtureConnector,
) -> None:
    page = await connector.get_object("131074")
    assert page.kind == "PAGE"

    attachment = await connector.get_object("ATT-att131200")
    assert attachment.kind == "ATTACHMENT"

    comment = await connector.get_object("COMMENT-c131300")
    assert comment.kind == "COMMENT"

    with pytest.raises(NotFound):
        await connector.get_object("does-not-exist")


async def test_get_content_fetches_page_body_on_demand(
    connector: ConfluenceFixtureConnector,
) -> None:
    content = await connector.get_content("131074")
    assert "SSO" in (content.text or "")


async def test_get_links_extracts_mentions_from_page_body(
    connector: ConfluenceFixtureConnector,
) -> None:
    links = await connector.get_links("131074")
    refs = {link.target_ref for link in links}
    assert "PR-42" in refs
    assert "AB#312" in refs


async def test_get_acl_reference(connector: ConfluenceFixtureConnector) -> None:
    ref = await connector.get_acl_reference("98305")
    assert ref.acl_ref["space"] == "TALENT"


async def test_get_changes_is_always_empty(connector: ConfluenceFixtureConnector) -> None:
    changes = await connector.get_changes()
    assert changes.items == []
    assert changes.has_more is False
