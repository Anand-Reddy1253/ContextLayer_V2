from context_fabric.connectors.teams import mapper
from context_fabric.domain.connector_types import (
    ACLReference,
    SourceContainer,
    SourceContent,
    SourceObject,
)

CHANNEL_RAW = {
    "id": "19:identity-squad@thread.tacv2",
    "displayName": "identity-squad",
    "description": "Identity Squad's main channel",
    "webUrl": "https://teams.microsoft.com/l/channel/identity-squad",
}

MESSAGE_RAW = {
    "id": "1700000000001",
    "channel_id": "19:identity-squad@thread.tacv2",
    "author": "Priya Shah",
    "created": "2026-08-20T09:15:00Z",
    "body_text": "Heads up — SSO rollout is blocked on TALENT-3. See AB#312, PR-42, "
    "and acme/talentflow-api#7.",
    "content_type": "text/plain",
    "url": "https://teams.microsoft.com/l/message/x/1700000000001",
}

REPLY_RAW = {
    "id": "1700000000003",
    "channel_id": "19:identity-squad@thread.tacv2",
    "message_id": "1700000000001",
    "author": "Diego Alvarez",
    "created": "2026-08-20T09:45:00Z",
    "body_text": "On it.",
    "content_type": "text/plain",
    "url": "https://teams.microsoft.com/l/message/x/1700000000003",
}


def test_map_channel() -> None:
    obj = mapper.map_channel(CHANNEL_RAW)
    assert isinstance(obj, SourceContainer)
    assert obj.kind == "CHANNEL"
    assert obj.native_id == "19:identity-squad@thread.tacv2"


def test_map_message_parents_to_channel() -> None:
    obj = mapper.map_message(MESSAGE_RAW)
    assert isinstance(obj, SourceObject)
    assert obj.kind == "MESSAGE"
    assert obj.parent_native_id == "19:identity-squad@thread.tacv2"
    assert "body_text" not in obj.attributes  # ADR-003: not eagerly duplicated
    assert obj.attributes["author"] == "Priya Shah"


def test_map_reply_parents_to_message() -> None:
    obj = mapper.map_reply(REPLY_RAW)
    assert obj.kind == "MESSAGE_REPLY"
    assert obj.parent_native_id == "1700000000001"


def test_map_tombstone() -> None:
    obj = mapper.map_tombstone("1700000000001", "MESSAGE")
    assert obj.deleted is True


def test_map_content_uses_content_type() -> None:
    content = mapper.map_content("1700000000001", MESSAGE_RAW)
    assert isinstance(content, SourceContent)
    assert content.mime_type == "text/plain"
    assert "SSO rollout" in (content.text or "")


def test_map_links_extracts_all_known_reference_shapes() -> None:
    links = mapper.map_links(MESSAGE_RAW)
    refs = {link.target_ref for link in links}
    assert refs == {"AB#312", "PR-42", "acme/talentflow-api#7", "TALENT-3"}


def test_map_links_returns_empty_for_plain_text() -> None:
    assert mapper.map_links({"id": "x", "body_text": "Nothing to see here."}) == []


def test_map_acl() -> None:
    ref = mapper.map_acl(
        {"native_id": "1700000000001", "acl_ref": {"channel": "19:identity-squad@thread.tacv2"}}
    )
    assert isinstance(ref, ACLReference)
    assert ref.acl_ref["channel"] == "19:identity-squad@thread.tacv2"
