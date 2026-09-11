"""Microsoft Teams live-mode connector, following the same fast-tracked
pattern as connectors/confluence/live.py and connectors/jira/live.py, but
with a genuinely different auth model: Microsoft Graph uses OAuth2
client-credentials (app-only), not a single opaque PAT or Basic auth.

Auth flow: a lazy POST to
`https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token` with
`client_id` + `client_secret` (grant_type=client_credentials, scope
`https://graph.microsoft.com/.default`) exchanges for a Bearer access
token, cached for the lifetime of this connector instance (a sync run) —
no refresh-on-expiry handling, since a sync run is short-lived relative
to a token's ~1 hour lifetime; this is a documented simplification, not
an oversight. `client_id`/`tenant_id`/`team_id` are plain config (not
secrets, same treatment as ADO's org_url/GitHub's org); `client_secret` is
the connection's single encrypted `credential`.

Required Graph API **application** permissions (admin-consented, not
delegated — this connector never acts as a signed-in user):
`ChannelMessage.Read.All`, `Channel.ReadBasic.All`, `Team.ReadBasic.All`.

Entity types (docs/CONNECTORS.md "Entity type selection"): which of
messages / replies this connector instance fetches is chosen per-
connection at creation time (config.entity_types) — see ENTITY_TYPES
below. Channels themselves are always listed as containers (the pick-able
unit via config.selected_containers, docs/UI.md "Connectors" picker),
scoped to the one Team named by config.team_id — a connection covers one
Team, the same way an ADO connection covers one org.

Known simplifications:
  - get_acl_reference returns {"channel": <id>} — no real Teams
    membership/permission check.
  - get_changes returns an always-empty page — no incremental delta feed
    implemented yet (Graph's delta query API would be the real mechanism).
  - No token refresh — see auth flow note above.

Every HTTP call goes through LiveConnectorBase.call_with_retry and
raise_for_status_category (401/403 -> AuthError, 404 -> NotFound, 429 ->
RateLimited, 5xx -> Transient, other 4xx -> Permanent) — including the
token exchange itself, so a bad client_secret surfaces as AuthError like
any other auth failure, not a separate error shape.
"""

from __future__ import annotations

from typing import Any, ClassVar

import httpx

from context_fabric.connectors.base import DEFAULT_TIMEOUT, LiveConnectorBase
from context_fabric.connectors.teams import mapper
from context_fabric.domain.connector_types import (
    ACLReference,
    ChangePage,
    Page,
    SourceContainer,
    SourceContent,
    SourceLink,
    SourceObject,
)
from context_fabric.domain.errors import NotFound

_GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"
_TOKEN_SCOPE = "https://graph.microsoft.com/.default"


class TeamsLiveConnector(LiveConnectorBase):
    source_system = "teams"

    ENTITY_TYPES: ClassVar[dict[str, str]] = {
        "messages": "Messages",
        "replies": "Replies",
    }

    def __init__(
        self,
        tenant_id: str,
        *,
        team_id: str,
        client_id: str,
        client_secret: str,
        timeout: httpx.Timeout = DEFAULT_TIMEOUT,
        max_attempts: int = 5,
        entity_types: list[str] | None = None,
        selected_containers: list[str] | None = None,
    ) -> None:
        super().__init__(_GRAPH_BASE_URL, timeout=timeout, max_attempts=max_attempts)
        self._tenant_id = tenant_id
        self._team_id = team_id
        self._client_id = client_id
        self._client_secret = client_secret
        self._access_token: str | None = None

        self._entity_types = set(entity_types) if entity_types else set(self.ENTITY_TYPES)
        self._selected_containers = set(selected_containers) if selected_containers else None

        self._channels_raw: list[dict[str, Any]] | None = None
        self._messages_by_channel: dict[str, list[dict[str, Any]]] = {}
        self._message_by_native_id: dict[str, dict[str, Any]] = {}
        self._replies_by_message: dict[str, list[dict[str, Any]]] = {}
        self._reply_by_native_id: dict[str, dict[str, Any]] = {}

    # -- auth + low-level HTTP -----------------------------------------

    async def _ensure_token(self) -> None:
        if self._access_token is not None:
            return

        async def do_call() -> httpx.Response:
            token_url = f"https://login.microsoftonline.com/{self._tenant_id}/oauth2/v2.0/token"
            async with httpx.AsyncClient(timeout=self.client.timeout) as token_client:
                response = await token_client.post(
                    token_url,
                    data={
                        "client_id": self._client_id,
                        "client_secret": self._client_secret,
                        "scope": _TOKEN_SCOPE,
                        "grant_type": "client_credentials",
                    },
                )
            self.raise_for_status_category(response)
            return response

        response = await self.call_with_retry(do_call)
        self._access_token = response.json()["access_token"]
        self.client.headers["Authorization"] = f"Bearer {self._access_token}"

    async def _request(self, method: str, url: str, **kwargs: Any) -> dict[str, Any]:
        await self._ensure_token()

        async def do_call() -> httpx.Response:
            response = await self.client.request(method, url, **kwargs)
            self.raise_for_status_category(response)
            return response

        response = await self.call_with_retry(do_call)
        result: dict[str, Any] = response.json()
        return result

    async def _paginated(self, url: str, **params: Any) -> list[dict[str, Any]]:
        """Graph API pagination via `@odata.nextLink` — a full absolute
        URL that already carries every original query param, like
        Confluence v2's `_links.next` (connectors/confluence/live.py)."""
        results: list[dict[str, Any]] = []
        next_url: str | None = url
        next_params: dict[str, Any] | None = params
        while next_url:
            data = await self._request("GET", next_url, params=next_params)
            results.extend(data.get("value", []))
            next_url = data.get("@odata.nextLink")
            next_params = None
        return results

    # -- discovery / hierarchy ------------------------------------------

    def _apply_channel_filter(self, channels: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if self._selected_containers is None:
            return channels
        return [c for c in channels if c["id"] in self._selected_containers]

    async def discover_containers(self) -> list[SourceContainer]:
        raw = await self._paginated(f"/teams/{self._team_id}/channels")
        self._channels_raw = self._apply_channel_filter(raw)
        return [mapper.map_channel(c) for c in self._channels_raw]

    async def _channel_ids(self) -> set[str]:
        if self._channels_raw is None:
            await self.discover_containers()
        return {c["id"] for c in (self._channels_raw or [])}

    @staticmethod
    def _flatten(
        raw: dict[str, Any], *, channel_id: str, message_id: str | None = None
    ) -> dict[str, Any]:
        body = raw.get("body") or {}
        from_field = raw.get("from") or {}
        author = (from_field.get("user") or {}).get("displayName") or (
            from_field.get("application") or {}
        ).get("displayName")
        flattened = {
            "id": raw["id"],
            "channel_id": channel_id,
            "author": author,
            "created": raw.get("createdDateTime", ""),
            "body_text": body.get("content", ""),
            "content_type": "text/html" if body.get("contentType") == "html" else "text/plain",
            "url": raw.get("webUrl", ""),
        }
        if message_id is not None:
            flattened["message_id"] = message_id
        return flattened

    async def _ensure_messages_for_channel(self, channel_id: str) -> list[dict[str, Any]]:
        if channel_id not in self._messages_by_channel:
            raw_messages = await self._paginated(
                f"/teams/{self._team_id}/channels/{channel_id}/messages"
            )
            messages = [self._flatten(m, channel_id=channel_id) for m in raw_messages]
            self._messages_by_channel[channel_id] = messages
            for m in messages:
                self._message_by_native_id[m["id"]] = m
        return self._messages_by_channel[channel_id]

    async def _ensure_replies_for_message(
        self, channel_id: str, message_id: str
    ) -> list[dict[str, Any]]:
        if message_id not in self._replies_by_message:
            raw_replies = await self._paginated(
                f"/teams/{self._team_id}/channels/{channel_id}/messages/{message_id}/replies"
            )
            replies = [
                self._flatten(r, channel_id=channel_id, message_id=message_id) for r in raw_replies
            ]
            self._replies_by_message[message_id] = replies
            for r in replies:
                self._reply_by_native_id[r["id"]] = r
        return self._replies_by_message[message_id]

    async def list_children(self, parent_id: str, cursor: str | None = None) -> Page[SourceObject]:
        channel_ids = await self._channel_ids()

        if parent_id in channel_ids:
            if "messages" not in self._entity_types:
                return Page(items=[], next_cursor=None)
            messages = await self._ensure_messages_for_channel(parent_id)
            return Page(items=[mapper.map_message(m) for m in messages], next_cursor=None)

        if parent_id in self._message_by_native_id:
            if "replies" not in self._entity_types:
                return Page(items=[], next_cursor=None)
            channel_id = self._message_by_native_id[parent_id]["channel_id"]
            replies = await self._ensure_replies_for_message(channel_id, parent_id)
            return Page(items=[mapper.map_reply(r) for r in replies], next_cursor=None)

        return Page(items=[], next_cursor=None)

    # -- single-object lookups -------------------------------------------

    async def get_object(self, native_id: str) -> SourceObject:
        if native_id in self._message_by_native_id:
            return mapper.map_message(self._message_by_native_id[native_id])
        if native_id in self._reply_by_native_id:
            return mapper.map_reply(self._reply_by_native_id[native_id])
        raise NotFound(
            f"no Teams object with native_id={native_id!r}", source_system=self.source_system
        )

    async def get_content(self, native_id: str, version: str | None = None) -> SourceContent:
        if native_id in self._message_by_native_id:
            return mapper.map_content(native_id, self._message_by_native_id[native_id])
        if native_id in self._reply_by_native_id:
            return mapper.map_content(native_id, self._reply_by_native_id[native_id])
        raise NotFound(f"no content for native_id={native_id!r}", source_system=self.source_system)

    # -- change feed / links / acl ----------------------------------------

    async def get_changes(self, cursor: str | None = None) -> ChangePage:
        """No incremental delta feed implemented yet — see module
        docstring's "Known simplifications"."""
        return ChangePage(items=[], next_cursor=None, has_more=False)

    async def get_links(self, native_id: str) -> list[SourceLink]:
        if native_id in self._message_by_native_id:
            return mapper.map_links(self._message_by_native_id[native_id])
        if native_id in self._reply_by_native_id:
            return mapper.map_links(self._reply_by_native_id[native_id])
        return []

    async def get_acl_reference(self, native_id: str) -> ACLReference:
        channel_id = None
        if native_id in self._message_by_native_id:
            channel_id = self._message_by_native_id[native_id]["channel_id"]
        elif native_id in self._reply_by_native_id:
            channel_id = self._reply_by_native_id[native_id]["channel_id"]
        acl_ref = {"channel": channel_id} if channel_id else {}
        return ACLReference(native_id=native_id, acl_ref=acl_ref)
