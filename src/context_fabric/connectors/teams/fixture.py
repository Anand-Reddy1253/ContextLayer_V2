"""Microsoft Teams fixture-mode connector.

Reads fixtures/teams/*.json — no network, no credentials. Native
hierarchy: Channel -> Message -> Reply (docs/CONNECTORS.md), all within
one Team a connection is scoped to.

Known simplification: get_changes returns an always-empty page — no
fixture data modeling a deletion here yet, consistent with the other
fast-tracked connectors (azure_devops, github, confluence, jira).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from context_fabric.connectors.base import FixtureConnectorBase
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

_PAGE_SIZE = 2


class TeamsFixtureConnector(FixtureConnectorBase):
    source_system = "teams"

    def __init__(self, fixtures_dir: Path | None = None) -> None:
        super().__init__(fixtures_dir)
        self._channels_raw: list[dict[str, Any]] = self.load_json("channels.json")
        self._messages_raw: list[dict[str, Any]] = self.load_json("messages.json")
        self._replies_raw: list[dict[str, Any]] = self.load_json("replies.json")
        self._acl_raw: list[dict[str, Any]] = self.load_json("acl.json")

        self._channel_ids = {c["id"] for c in self._channels_raw}
        self._message_ids = {m["id"] for m in self._messages_raw}

    # -- discovery / hierarchy ------------------------------------------

    async def discover_containers(self) -> list[SourceContainer]:
        return [mapper.map_channel(c) for c in self._channels_raw]

    async def list_children(self, parent_id: str, cursor: str | None = None) -> Page[SourceObject]:
        return self._paginate(self._children_of(parent_id), cursor)

    def _children_of(self, parent_id: str) -> list[SourceObject]:
        if parent_id in self._channel_ids:
            return [
                mapper.map_message(m) for m in self._messages_raw if m["channel_id"] == parent_id
            ]
        if parent_id in self._message_ids:
            return [mapper.map_reply(r) for r in self._replies_raw if r["message_id"] == parent_id]
        return []

    @staticmethod
    def _paginate(items: list[SourceObject], cursor: str | None) -> Page[SourceObject]:
        start = int(cursor) if cursor else 0
        end = start + _PAGE_SIZE
        page_items = items[start:end]
        next_cursor = str(end) if end < len(items) else None
        return Page(items=page_items, next_cursor=next_cursor)

    # -- single-object lookups -------------------------------------------

    async def get_object(self, native_id: str) -> SourceObject:
        for m in self._messages_raw:
            if m["id"] == native_id:
                return mapper.map_message(m)
        for r in self._replies_raw:
            if r["id"] == native_id:
                return mapper.map_reply(r)
        raise NotFound(
            f"no Teams object with native_id={native_id!r}", source_system=self.source_system
        )

    async def get_content(self, native_id: str, version: str | None = None) -> SourceContent:
        for m in self._messages_raw:
            if m["id"] == native_id:
                return mapper.map_content(native_id, m)
        for r in self._replies_raw:
            if r["id"] == native_id:
                return mapper.map_content(native_id, r)
        raise NotFound(f"no content for native_id={native_id!r}", source_system=self.source_system)

    # -- change feed / links / acl ----------------------------------------

    async def get_changes(self, cursor: str | None = None) -> ChangePage:
        return ChangePage(items=[], next_cursor=None, has_more=False)

    async def get_links(self, native_id: str) -> list[SourceLink]:
        for m in self._messages_raw:
            if m["id"] == native_id:
                return mapper.map_links(m)
        for r in self._replies_raw:
            if r["id"] == native_id:
                return mapper.map_links(r)
        return []

    async def get_acl_reference(self, native_id: str) -> ACLReference:
        for raw in self._acl_raw:
            if raw["native_id"] == native_id:
                return mapper.map_acl(raw)
        raise NotFound(
            f"no ACL reference for native_id={native_id!r}", source_system=self.source_system
        )
