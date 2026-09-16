"""Confluence fixture-mode connector.

Reads fixtures/confluence/*.json — no network, no credentials. Native
hierarchy: Space -> Page -> child Page, with Attachments, Comments,
PERSON (authors/commenters), and LABEL nodes as leaves parented by the
page they belong to (docs/CONNECTORS.md). Always emits every entity type
— unlike live.py, fixture mode has no per-connection entity_types config
to gate on, and fixture data is small enough that there's no cost reason
to.

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
        # account_id -> display name, from the pages/comments fixture data
        # itself (fixture mode has no live user-lookup call to make).
        self._display_names: dict[str, str] = {
            **{
                p["authorId"]: p.get("authorName", p["authorId"])
                for p in self._pages_raw
                if p.get("authorId")
            },
            **{
                c["author"]: c.get("authorName", c["author"])
                for c in self._comments_raw
                if c.get("author")
            },
        }

    # -- discovery / hierarchy ------------------------------------------

    async def discover_containers(self) -> list[SourceContainer]:
        return [mapper.map_space(s) for s in self._spaces_raw]

    async def list_children(self, parent_id: str, cursor: str | None = None) -> Page[SourceObject]:
        return self._paginate(self._children_of(parent_id), cursor)

    def _children_of(self, parent_id: str) -> list[SourceObject]:
        # Ordering matters, not just presence: synchronization/
        # orchestrator.py upserts each item in list_children's own
        # returned order and calls get_links() on it *immediately* —
        # before ever calling list_children on that item itself. A page's
        # AUTHORED_BY/HAS_LABEL edges (emitted from the page's own
        # get_links()) can only resolve if the PERSON/LABEL node they
        # target was already upserted earlier in the *same* items list —
        # which means those dependency nodes must be emitted as this
        # page's *siblings*, before it, in whichever list_children call
        # first introduces the page. (A real bug this shape guards
        # against: LABEL used to be emitted as the page's own *child*,
        # discovered a full BFS level later than the page's own
        # get_links() call — which could never resolve, ever, on a fresh
        # sync.)
        if parent_id in self._space_ids:
            top_pages = [
                p
                for p in self._pages_raw
                if not p.get("parentId") and str(p["spaceId"]) == parent_id
            ]
            items: list[SourceObject] = []
            seen_authors: set[str] = set()
            for p in self._pages_raw:
                if str(p["spaceId"]) != parent_id:
                    continue
                account_id = p.get("authorId")
                if account_id and account_id not in seen_authors:
                    seen_authors.add(account_id)
                    items.append(
                        mapper.map_person(
                            account_id,
                            self._display_names.get(account_id),
                            parent_native_id=parent_id,
                        )
                    )
            seen_labels: set[str] = set()
            for p in top_pages:
                for name in p.get("labels", []) or []:
                    if name not in seen_labels:
                        seen_labels.add(name)
                        items.append(mapper.map_label(name, parent_native_id=parent_id))
            items += [mapper.map_page(p) for p in top_pages]
            return items
        if parent_id in self._page_ids:
            child_pages = [
                p
                for p in self._pages_raw
                if str(p.get("parentId") or "") == parent_id
            ]
            items = []
            seen_authors = set()
            for p in child_pages:
                account_id = p.get("authorId")
                if account_id and account_id not in seen_authors:
                    seen_authors.add(account_id)
                    items.append(
                        mapper.map_person(
                            account_id,
                            self._display_names.get(account_id),
                            parent_native_id=parent_id,
                        )
                    )
            seen_labels = set()
            for p in child_pages:
                for name in p.get("labels", []) or []:
                    if name not in seen_labels:
                        seen_labels.add(name)
                        items.append(mapper.map_label(name, parent_native_id=parent_id))
            items += [mapper.map_page(p) for p in child_pages]
            items += [
                mapper.map_attachment(a)
                for a in self._attachments_raw
                if str(a["pageId"]) == parent_id
            ]
            page_comments = [c for c in self._comments_raw if str(c["pageId"]) == parent_id]
            seen_comment_authors: set[str] = set()
            for c in page_comments:
                account_id = c.get("author")
                if account_id and account_id not in seen_comment_authors:
                    seen_comment_authors.add(account_id)
                    items.append(
                        mapper.map_person(
                            account_id,
                            self._display_names.get(account_id),
                            parent_native_id=parent_id,
                        )
                    )
            items += [mapper.map_comment(c) for c in page_comments]
            return items
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
        raise NotFound(f"no content for native_id={native_id!r}", source_system=self.source_system)

    # -- change feed / links / acl ----------------------------------------

    async def get_changes(self, cursor: str | None = None) -> ChangePage:
        return ChangePage(items=[], next_cursor=None, has_more=False)

    async def get_links(self, native_id: str) -> list[SourceLink]:
        for p in self._pages_raw:
            if str(p["id"]) == native_id:
                links = mapper.extract_structured_links(native_id, p.get("body", ""))
                links += mapper.map_page_relationship_links(
                    native_id,
                    space_native_id=str(p["spaceId"]),
                    author_account_id=p.get("authorId"),
                    label_names=p.get("labels", []),
                )
                return links
        for c in self._comments_raw:
            if f"COMMENT-{c['id']}" == native_id:
                links = mapper.extract_structured_links(
                    native_id, c.get("body", ""), location="comment"
                )
                links += mapper.map_comment_relationship_links(
                    native_id, author_account_id=c.get("author")
                )
                return links
        return []

    async def get_acl_reference(self, native_id: str) -> ACLReference:
        for raw in self._acl_raw:
            if raw["native_id"] == native_id:
                return mapper.map_acl(raw)
        raise NotFound(
            f"no ACL reference for native_id={native_id!r}", source_system=self.source_system
        )
