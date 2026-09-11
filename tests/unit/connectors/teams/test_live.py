from context_fabric.connectors.teams.live import TeamsLiveConnector


def test_flatten_extracts_user_author_from_graph_shape() -> None:
    raw = {
        "id": "1",
        "createdDateTime": "2026-08-20T09:15:00Z",
        "from": {"user": {"displayName": "Priya Shah"}},
        "body": {"contentType": "text", "content": "hello"},
        "webUrl": "https://teams.microsoft.com/l/message/x/1",
    }
    flattened = TeamsLiveConnector._flatten(raw, channel_id="chan-1")
    assert flattened["author"] == "Priya Shah"
    assert flattened["channel_id"] == "chan-1"
    assert flattened["content_type"] == "text/plain"
    assert "message_id" not in flattened


def test_flatten_falls_back_to_application_author_for_bot_messages() -> None:
    raw = {
        "id": "2",
        "createdDateTime": "2026-08-20T09:15:00Z",
        "from": {"application": {"displayName": "CI Bot"}},
        "body": {"contentType": "html", "content": "<p>build failed</p>"},
        "webUrl": "https://teams.microsoft.com/l/message/x/2",
    }
    flattened = TeamsLiveConnector._flatten(raw, channel_id="chan-1")
    assert flattened["author"] == "CI Bot"
    assert flattened["content_type"] == "text/html"


def test_flatten_includes_message_id_for_replies() -> None:
    raw = {
        "id": "3",
        "createdDateTime": "2026-08-20T09:15:00Z",
        "from": {},
        "body": {"contentType": "text", "content": "reply"},
        "webUrl": "",
    }
    flattened = TeamsLiveConnector._flatten(raw, channel_id="chan-1", message_id="1")
    assert flattened["message_id"] == "1"
