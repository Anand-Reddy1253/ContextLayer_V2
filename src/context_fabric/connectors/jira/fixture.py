"""Jira fixture-mode connector.

Reads fixtures/jira/*.json — no network, no credentials. Native
hierarchy: Project -> Issue -> child Issue (sub-tasks / epic children),
with Comments as leaves parented by the issue they belong to
(docs/CONNECTORS.md).

Known simplification: get_changes returns an always-empty page — no
fixture data modeling a deletion here yet, consistent with the other
fast-tracked connectors (azure_devops, github, confluence).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from context_fabric.connectors.base import FixtureConnectorBase
from context_fabric.connectors.jira import mapper
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


class JiraFixtureConnector(FixtureConnectorBase):
    source_system = "jira"

    def __init__(self, fixtures_dir: Path | None = None) -> None:
        super().__init__(fixtures_dir)
        self._projects_raw: list[dict[str, Any]] = self.load_json("projects.json")
        self._issues_raw: list[dict[str, Any]] = self.load_json("issues.json")
        self._comments_raw: list[dict[str, Any]] = self.load_json("comments.json")
        self._acl_raw: list[dict[str, Any]] = self.load_json("acl.json")

        self._project_keys = {p["key"] for p in self._projects_raw}
        self._issue_keys = {i["key"] for i in self._issues_raw}

    # -- discovery / hierarchy ------------------------------------------

    async def discover_containers(self) -> list[SourceContainer]:
        return [mapper.map_project(p) for p in self._projects_raw]

    async def list_children(
        self, parent_id: str, cursor: str | None = None
    ) -> Page[SourceObject]:
        return self._paginate(self._children_of(parent_id), cursor)

    def _children_of(self, parent_id: str) -> list[SourceObject]:
        if parent_id in self._project_keys:
            return [
                mapper.map_issue(i)
                for i in self._issues_raw
                if not i.get("parent_key") and i["project_key"] == parent_id
            ]
        if parent_id in self._issue_keys:
            children = [
                mapper.map_issue(i) for i in self._issues_raw if i.get("parent_key") == parent_id
            ]
            children += [
                mapper.map_comment(c, parent_id)
                for c in self._comments_raw
                if c["issue_key"] == parent_id
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
        for i in self._issues_raw:
            if i["key"] == native_id:
                return mapper.map_issue(i)
        for c in self._comments_raw:
            if f"COMMENT-{c['id']}" == native_id:
                return mapper.map_comment(c, c["issue_key"])
        raise NotFound(
            f"no Jira object with native_id={native_id!r}", source_system=self.source_system
        )

    async def get_content(self, native_id: str, version: str | None = None) -> SourceContent:
        for i in self._issues_raw:
            if i["key"] == native_id:
                return mapper.map_content(native_id, i)
        for c in self._comments_raw:
            if f"COMMENT-{c['id']}" == native_id:
                return mapper.map_comment_content(native_id, c)
        raise NotFound(f"no content for native_id={native_id!r}", source_system=self.source_system)

    # -- change feed / links / acl ----------------------------------------

    async def get_changes(self, cursor: str | None = None) -> ChangePage:
        return ChangePage(items=[], next_cursor=None, has_more=False)

    async def get_links(self, native_id: str) -> list[SourceLink]:
        for i in self._issues_raw:
            if i["key"] == native_id:
                return mapper.map_links(i)
        for c in self._comments_raw:
            if f"COMMENT-{c['id']}" == native_id:
                return mapper.map_comment_links(c, c["issue_key"])
        return []

    async def get_acl_reference(self, native_id: str) -> ACLReference:
        for raw in self._acl_raw:
            if raw["native_id"] == native_id:
                return mapper.map_acl(raw)
        raise NotFound(
            f"no ACL reference for native_id={native_id!r}", source_system=self.source_system
        )
