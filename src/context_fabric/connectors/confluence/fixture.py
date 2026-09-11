"""Confluence fixture-mode connector.

Reads fixtures/confluence/*.json — no network, no credentials. Native
hierarchy: Space -> Page -> child Page, with Attachments and Comments as
leaves parented by the page they belong to (docs/CONNECTORS.md).

Known simplification: get_changes returns an always-empty page — unlike
ADO's Recycle Bin or GitHub's absent delta feed, there's no fixture data
modeling a deletion here yet; a real live-mode implementation would need
Confluence's own audit/trash APIs, out of scope for this fast-tracked
connector's first pass.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from context_fabric.connectors.base import FixtureConnectorBase
from context_fabric.connectors.confluence import mapper
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


class ConfluenceFixtureConnector(FixtureConnectorBase):
    source_system = "confluence"

    def __init__(self, fixtures_dir: Path | None = None) -> None:
        super().__init__(fixtures_dir)
        self._spaces_raw: list[dict[str, Any]] = self.load_json("spaces.json")
        self._pages_raw: list[dict[str, Any]] = self.load_json("pages.json")
        self._attachments_raw: list[dict[str, Any]] = self.load_json("attachments.json")
        self._comments_raw: list[dict[str, Any]] = self.load_json("comments.json")
        self._acl_raw: list[dict[str, Any]] = self.load_json("acl.json")

        self._space_ids = {str(s["id"]) for s in self._spaces_raw}
        self._page_ids = {str(p["id"]) for p in self._pages_raw}

    # -- discovery / hierarchy ------------------------------------------

    async def discover_containers(self) -> list[SourceContainer]:
        return [mapper.map_space(s) for s in self._spaces_raw]

    async def list_children(
        self, parent_id: str, cursor: str | None = None
    ) -> Page[SourceObject]:
        return self._paginate(self._children_of(parent_id), cursor)

    def _children_of(self, parent_id: str) -> list[SourceObject]:
        if parent_id in self._space_ids:
            return [
                mapper.map_page(p)
                for p in self._pages_raw
                if not p.get("parentId") and str(p["spaceId"]) == parent_id
            ]
        if parent_id in self._page_ids:
            children = [
                mapper.map_page(p)
                for p in self._pages_raw
                if str(p.get("parentId") or "") == parent_id
            ]
            children += [
                mapper.map_attachment(a)
                for a in self._attachments_raw
                if str(a["pageId"]) == parent_id
            ]
            children += [
                mapper.map_comment(c) for c in self._comments_raw if str(c["pageId"]) == parent_id
            ]
            return children
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
        for p in self._pages_raw:
            if str(p["id"]) == native_id:
                return mapper.map_page(p)
        for a in self._attachments_raw:
            if f"ATT-{a['id']}" == native_id:
                return mapper.map_attachment(a)
        for c in self._comments_raw:
            if f"COMMENT-{c['id']}" == native_id:
                return mapper.map_comment(c)
        raise NotFound(
            f"no Confluence object with native_id={native_id!r}", source_system=self.source_system
        )

    async def get_content(self, native_id: str, version: str | None = None) -> SourceContent:
        for p in self._pages_raw:
            if str(p["id"]) == native_id:
                return mapper.map_page_content(native_id, p)
        for c in self._comments_raw:
            if f"COMMENT-{c['id']}" == native_id:
                return mapper.map_comment_content(native_id, c)
        raise NotFound(
            f"no content for native_id={native_id!r}", source_system=self.source_system
        )

    # -- change feed / links / acl ----------------------------------------

    async def get_changes(self, cursor: str | None = None) -> ChangePage:
        return ChangePage(items=[], next_cursor=None, has_more=False)

    async def get_links(self, native_id: str) -> list[SourceLink]:
        for p in self._pages_raw:
            if str(p["id"]) == native_id:
                return mapper.map_links_from_text(native_id, p.get("body", ""))
        for c in self._comments_raw:
            if f"COMMENT-{c['id']}" == native_id:
                return mapper.map_links_from_text(native_id, c.get("body", ""))
        return []

    async def get_acl_reference(self, native_id: str) -> ACLReference:
        for raw in self._acl_raw:
            if raw["native_id"] == native_id:
                return mapper.map_acl(raw)
        raise NotFound(
            f"no ACL reference for native_id={native_id!r}", source_system=self.source_system
        )
