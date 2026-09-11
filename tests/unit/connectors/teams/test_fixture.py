import pytest

from context_fabric.connectors.teams.fixture import TeamsFixtureConnector
from context_fabric.domain.errors import NotFound


@pytest.fixture
def connector() -> TeamsFixtureConnector:
    return TeamsFixtureConnector()


async def test_discover_containers_returns_channels(connector: TeamsFixtureConnector) -> None:
    containers = await connector.discover_containers()
    assert {c.native_id for c in containers} == {
        "19:identity-squad@thread.tacv2",
        "19:platform-eng@thread.tacv2",
    }
    assert all(c.kind == "CHANNEL" for c in containers)


async def test_list_children_walks_channel_to_message_to_reply(
    connector: TeamsFixtureConnector,
) -> None:
    channel_children = await connector.list_children("19:identity-squad@thread.tacv2")
    assert {c.native_id for c in channel_children.items} == {"1700000000001", "1700000000002"}

    message_children = await connector.list_children("1700000000001")
    assert [c.native_id for c in message_children.items] == ["1700000000003"]
    assert message_children.items[0].kind == "MESSAGE_REPLY"


async def test_get_object_resolves_message_and_reply(connector: TeamsFixtureConnector) -> None:
    message = await connector.get_object("1700000000001")
    assert message.kind == "MESSAGE"

    reply = await connector.get_object("1700000000003")
    assert reply.kind == "MESSAGE_REPLY"

    with pytest.raises(NotFound):
        await connector.get_object("does-not-exist")


async def test_get_content_fetches_message_body_on_demand(
    connector: TeamsFixtureConnector,
) -> None:
    content = await connector.get_content("1700000000001")
    assert "SSO rollout" in (content.text or "")


async def test_get_links_extracts_mentions_from_message_body(
    connector: TeamsFixtureConnector,
) -> None:
    links = await connector.get_links("1700000000001")
    refs = {link.target_ref for link in links}
    assert "AB#312" in refs


async def test_get_acl_reference(connector: TeamsFixtureConnector) -> None:
    ref = await connector.get_acl_reference("1700000000001")
    assert ref.acl_ref["channel"] == "19:identity-squad@thread.tacv2"


async def test_get_changes_is_always_empty(connector: TeamsFixtureConnector) -> None:
    changes = await connector.get_changes()
    assert changes.items == []
    assert changes.has_more is False
