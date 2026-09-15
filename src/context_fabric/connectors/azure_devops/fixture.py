"""Azure DevOps fixture-mode connector.

Reads fixtures/azure_devops/*.json — no network, no credentials. Native
hierarchy: Project -> Area Path -> Epic -> Feature -> Story/Task/Bug
(docs/CONNECTORS.md). Pull requests and builds are separate SourceObject
kinds, parented by repository/build-definition id respectively.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from context_fabric.connectors.azure_devops import mapper
from context_fabric.connectors.base import FixtureConnectorBase
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
_CHANGES_PAGE_SIZE = 1


class AzureDevOpsFixtureConnector(FixtureConnectorBase):
    source_system = "azure_devops"

    def __init__(self, fixtures_dir: Path | None = None) -> None:
        super().__init__(fixtures_dir)
        self._projects_raw: list[dict[str, Any]] = self.load_json("projects.json")
        self._area_paths_raw: list[dict[str, Any]] = self.load_json("area_paths.json")
        self._pull_requests_raw: list[dict[str, Any]] = self.load_json("pull_requests.json")
        self._builds_raw: list[dict[str, Any]] = self.load_json("builds.json")
        self._changes_raw: dict[str, Any] = self.load_json("changes.json")
        self._acl_raw: list[dict[str, Any]] = self.load_json("acl.json")

        work_items_raw: list[dict[str, Any]] = [
            *self.load_json("work_items/epics.json"),
            *self.load_json("work_items/features.json"),
            *self.load_json("work_items/stories.json"),
            *self.load_json("work_items/bugs.json"),
        ]
        self._work_items_raw_by_id: dict[str, dict[str, Any]] = {
            str(raw["id"]): raw for raw in work_items_raw
        }
        self._project_ids = {p["id"] for p in self._projects_raw}

    # -- discovery / hierarchy ------------------------------------------

    async def discover_containers(self) -> list[SourceContainer]:
        return [mapper.map_project(p) for p in self._projects_raw]

    async def list_children(self, parent_id: str, cursor: str | None = None) -> Page[SourceObject]:
        children = self._children_of(parent_id)
        return self._paginate(children, cursor)

    def _children_of(self, parent_id: str) -> list[SourceObject]:
        if parent_id in self._project_ids:
            return [
                mapper.map_area_path(a) for a in self._area_paths_raw if a["project"] == parent_id
            ]
        return [
            mapped
            for raw in self._work_items_raw_by_id.values()
            if (mapped := mapper.map_work_item(raw)).parent_native_id == parent_id
        ]

    @staticmethod
    def _paginate(items: list[SourceObject], cursor: str | None) -> Page[SourceObject]:
        start = int(cursor) if cursor else 0
        end = start + _PAGE_SIZE
        page_items = items[start:end]
        next_cursor = str(end) if end < len(items) else None
        return Page(items=page_items, next_cursor=next_cursor)

    # -- single-object lookups -------------------------------------------

    async def get_object(self, native_id: str) -> SourceObject:
        if native_id in self._work_items_raw_by_id:
            return mapper.map_work_item(self._work_items_raw_by_id[native_id])
        for raw in self._pull_requests_raw:
            if f"PR-{raw['pullRequestId']}" == native_id:
                return mapper.map_pull_request(raw)
        for raw in self._builds_raw:
            if f"BUILD-{raw['id']}" == native_id:
                return mapper.map_build(raw)
        for raw in self._area_paths_raw:
            if raw["id"] == native_id:
                return mapper.map_area_path(raw)
        raise NotFound(
            f"no Azure DevOps object with native_id={native_id!r}",
            source_system=self.source_system,
        )

    async def get_content(self, native_id: str, version: str | None = None) -> SourceContent:
        raw = self._work_items_raw_by_id.get(native_id)
        if raw is None:
            raise NotFound(
                f"no content for native_id={native_id!r}", source_system=self.source_system
            )
        return mapper.map_content(native_id, raw)

    # -- change feed / links / acl ----------------------------------------

    async def get_changes(self, cursor: str | None = None) -> ChangePage:
        all_changes = self._changes_raw["items"]
        start = int(cursor) if cursor else 0
        end = start + _CHANGES_PAGE_SIZE
        page_raw = all_changes[start:end]
        next_cursor = str(end) if end < len(all_changes) else None

        items: list[SourceObject] = []
        for change in page_raw:
            native_id = str(change["id"])
            kind = mapper.WORK_ITEM_TYPE_TO_KIND.get(change.get("workItemType", ""), "WORK_ITEM")
            if change["changeType"] == "deleted":
                items.append(mapper.map_tombstone(native_id, kind))
                continue
            raw = self._work_items_raw_by_id.get(native_id)
            items.append(
                mapper.map_work_item(raw) if raw else mapper.map_tombstone(native_id, kind)
            )

        return ChangePage(items=items, next_cursor=next_cursor, has_more=next_cursor is not None)

    async def get_links(self, native_id: str) -> list[SourceLink]:
        raw = self._work_items_raw_by_id.get(native_id)
        if raw is None:
            return []
        return mapper.map_links(raw)

    async def get_acl_reference(self, native_id: str) -> ACLReference:
        for raw in self._acl_raw:
            if raw["native_id"] == native_id:
                return mapper.map_acl(raw)
        raise NotFound(
            f"no ACL reference for native_id={native_id!r}", source_system=self.source_system
        )
