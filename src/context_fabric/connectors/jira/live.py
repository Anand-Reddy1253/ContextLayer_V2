"""Jira Cloud live-mode connector, following the same fast-tracked
pattern as connectors/confluence/live.py (same Atlassian Cloud auth
shape) and connectors/azure_devops/live.py / connectors/github/live.py.

Reuses connectors/jira/mapper.py unchanged — this module's only job is
turning Jira's real REST API v3 shapes into the flattened dicts mapper.py
expects (`{"key", "project_key", "parent_key", "summary", "issue_type",
"status", "assignee", "description_text", "url", "updated",
"issuelinks"}` for issues).

Auth: Jira Cloud uses the same Basic auth (account email + API token) as
Confluence Cloud — the two products share Atlassian's auth model, and in
practice the same API token often works for both, though this is wired as
an entirely separate connector connection/config since a user may only
have access to one of the two.

Entity types (docs/CONNECTORS.md "Entity type selection"): which of
issues / comments this connector instance fetches is chosen per-connection
at creation time (config.entity_types) — see ENTITY_TYPES below. Projects
themselves are always listed as containers (the pick-able unit via
config.selected_containers, docs/UI.md "Connectors" picker).

Known simplifications:
  - get_acl_reference returns {"project": <key>} — no real Jira
    permission-scheme check.
  - get_changes returns an always-empty page — no incremental delta feed
    implemented yet (would need Jira's /search with a `updated >=` JQL
    clause driving a proper cursor, or the changelog API).
  - issuelinks' relationship type is collapsed to depends_on/relates_to
    via a name-substring heuristic (mapper._link_kind_for_type) rather
    than modeling Jira's full configurable link-type table.

Every HTTP call goes through LiveConnectorBase.call_with_retry and
raise_for_status_category (401/403 -> AuthError, 404 -> NotFound, 429 ->
RateLimited, 5xx -> Transient, other 4xx -> Permanent).
"""

from __future__ import annotations

import base64
from typing import Any, ClassVar
from urllib.parse import urlsplit, urlunsplit

import httpx

from context_fabric.connectors.base import DEFAULT_TIMEOUT, LiveConnectorBase
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

_API_VERSION_PATH = "/rest/api/3"
_PAGE_SIZE = 100
_ISSUE_FIELDS = (
    "summary,issuetype,status,assignee,parent,project,issuelinks,description,updated,labels"
)


def _normalize_site_url(site_url: str) -> str:
    """Same fix as confluence/live.py's _normalize_site_url — strips
    anything beyond the bare site origin so a URL copied while inside a
    project or issue doesn't double up with this connector's own
    "/rest/api/3/..." prefix."""
    parts = urlsplit(site_url.strip().rstrip("/"))
    return urlunsplit((parts.scheme, parts.netloc, "", "", ""))


class JiraLiveConnector(LiveConnectorBase):
    source_system = "jira"

    ENTITY_TYPES: ClassVar[dict[str, str]] = {
        "issues": "Issues",
        "comments": "Comments",
    }

    def __init__(
        self,
        site_url: str,
        *,
        email: str,
        api_token: str,
        timeout: httpx.Timeout = DEFAULT_TIMEOUT,
        max_attempts: int = 5,
        entity_types: list[str] | None = None,
        selected_containers: list[str] | None = None,
    ) -> None:
        site_url = _normalize_site_url(site_url)
        token = base64.b64encode(f"{email}:{api_token}".encode()).decode("ascii")
        headers = {"Authorization": f"Basic {token}", "Accept": "application/json"}
        super().__init__(
            f"{site_url}{_API_VERSION_PATH}",
            timeout=timeout,
            headers=headers,
            max_attempts=max_attempts,
        )
        self._entity_types = set(entity_types) if entity_types else set(self.ENTITY_TYPES)
        self._selected_containers = set(selected_containers) if selected_containers else None

        self._projects_raw: list[dict[str, Any]] | None = None
        self._issues_by_project: dict[str, list[dict[str, Any]]] = {}
        self._issue_by_key: dict[str, dict[str, Any]] = {}
        self._comments_by_issue: dict[str, list[dict[str, Any]]] = {}
        self._comment_by_native_id: dict[str, dict[str, Any]] = {}

    # -- low-level HTTP -----------------------------------------------

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        async def do_call() -> httpx.Response:
            response = await self.client.request(method, path, **kwargs)
            self.raise_for_status_category(response)
            return response

        response = await self.call_with_retry(do_call)
        result: dict[str, Any] = response.json()
        return result

    async def _paginated(
        self, path: str, *, items_key: str, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Jira v3's classic pagination — startAt/maxResults/total,
        unlike Confluence v2's cursor links."""
        results: list[dict[str, Any]] = []
        start_at = 0
        while True:
            page_params = {"startAt": start_at, "maxResults": _PAGE_SIZE, **(params or {})}
            data = await self._request("GET", path, params=page_params)
            items = data.get(items_key, [])
            results.extend(items)
            total = data.get("total", len(results))
            start_at += len(items)
            if not items or start_at >= total:
                break
        return results

    # -- discovery / hierarchy ------------------------------------------

    def _apply_project_filter(self, projects: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if self._selected_containers is None:
            return projects
        selected = self._selected_containers
        return [p for p in projects if p["key"] in selected or str(p.get("id")) in selected]

    async def discover_containers(self) -> list[SourceContainer]:
        raw = await self._paginated("/project/search", items_key="values")
        projects = [
            {
                "key": p["key"],
                "name": p.get("name", p["key"]),
                "description": p.get("description", ""),
                "url": (p.get("self", "") or "").replace("/rest/api/3/project/", "/browse/"),
            }
            for p in raw
        ]
        self._projects_raw = self._apply_project_filter(projects)
        return [mapper.map_project(p) for p in self._projects_raw]

    async def _project_keys(self) -> set[str]:
        if self._projects_raw is None:
            await self.discover_containers()
        return {p["key"] for p in (self._projects_raw or [])}

    @staticmethod
    def _flatten_issue(raw: dict[str, Any]) -> dict[str, Any]:
        fields = raw["fields"]
        parent = fields.get("parent")
        assignee = fields.get("assignee") or {}
        issuelinks = []
        for link in fields.get("issuelinks", []) or []:
            target = link.get("outwardIssue") or link.get("inwardIssue")
            issuelinks.append(
                {
                    "type_name": (link.get("type") or {}).get("name", ""),
                    "target_key": target.get("key") if target else None,
                }
            )
        return {
            "key": raw["key"],
            "project_key": fields["project"]["key"],
            "parent_key": parent.get("key") if parent else None,
            "summary": fields.get("summary", ""),
            "issue_type": (fields.get("issuetype") or {}).get("name", ""),
            "status": (fields.get("status") or {}).get("name", ""),
            "assignee": assignee.get("displayName"),
            "description_text": mapper.adf_to_text(fields.get("description") or {}),
            "url": raw.get("self", "").replace("/rest/api/3/issue/", "/browse/"),
            "updated": fields.get("updated", ""),
            "issuelinks": issuelinks,
            "labels": fields.get("labels", []) or [],
        }

    async def _ensure_issues_for_project(self, project_key: str) -> list[dict[str, Any]]:
        if project_key not in self._issues_by_project:
            raw_issues = await self._paginated(
                "/search",
                items_key="issues",
                params={
                    "jql": f"project={project_key} ORDER BY created ASC",
                    "fields": _ISSUE_FIELDS,
                },
            )
            issues = [self._flatten_issue(i) for i in raw_issues]
            self._issues_by_project[project_key] = issues
            for i in issues:
                self._issue_by_key[i["key"]] = i
        return self._issues_by_project[project_key]

    async def _ensure_comments_for_issue(self, issue_key: str) -> list[dict[str, Any]]:
        if issue_key not in self._comments_by_issue:
            raw_comments = await self._paginated(
                f"/issue/{issue_key}/comment", items_key="comments"
            )
            comments = []
            for c in raw_comments:
                comment = {
                    "id": c["id"],
                    "issue_key": issue_key,
                    "body_text": mapper.adf_to_text(c.get("body") or {}),
                    "author": (c.get("author") or {}).get("displayName", ""),
                    "url": c.get("self", "").replace("/rest/api/3", "/browse"),
                }
                comments.append(comment)
                self._comment_by_native_id[f"COMMENT-{comment['id']}"] = comment
            self._comments_by_issue[issue_key] = comments
        return self._comments_by_issue[issue_key]

    async def list_children(self, parent_id: str, cursor: str | None = None) -> Page[SourceObject]:
        project_keys = await self._project_keys()

        if parent_id in project_keys:
            if "issues" not in self._entity_types:
                return Page(items=[], next_cursor=None)
            issues = await self._ensure_issues_for_project(parent_id)
            items = [
                mapper.map_issue(i)
                for i in issues
                if not i.get("parent_key") and i["project_key"] == parent_id
            ]
            return Page(items=items, next_cursor=None)

        if parent_id in self._issue_by_key:
            items = []
            if "issues" in self._entity_types:
                project_key = self._issue_by_key[parent_id]["project_key"]
                issues = await self._ensure_issues_for_project(project_key)
                items += [mapper.map_issue(i) for i in issues if i.get("parent_key") == parent_id]
            if "comments" in self._entity_types:
                comments = await self._ensure_comments_for_issue(parent_id)
                items += [mapper.map_comment(c, parent_id) for c in comments]
            return Page(items=items, next_cursor=None)

        return Page(items=[], next_cursor=None)

    # -- single-object lookups -------------------------------------------

    async def get_object(self, native_id: str) -> SourceObject:
        if native_id in self._issue_by_key:
            return mapper.map_issue(self._issue_by_key[native_id])
        if native_id in self._comment_by_native_id:
            comment = self._comment_by_native_id[native_id]
            return mapper.map_comment(comment, comment["issue_key"])
        raise NotFound(
            f"no Jira object with native_id={native_id!r}", source_system=self.source_system
        )

    async def get_content(self, native_id: str, version: str | None = None) -> SourceContent:
        if native_id in self._issue_by_key:
            return mapper.map_content(native_id, self._issue_by_key[native_id])
        if native_id in self._comment_by_native_id:
            return mapper.map_comment_content(native_id, self._comment_by_native_id[native_id])
        raise NotFound(f"no content for native_id={native_id!r}", source_system=self.source_system)

    # -- change feed / links / acl ----------------------------------------

    async def get_changes(self, cursor: str | None = None) -> ChangePage:
        """No incremental delta feed implemented yet — see module
        docstring's "Known simplifications"."""
        return ChangePage(items=[], next_cursor=None, has_more=False)

    async def get_links(self, native_id: str) -> list[SourceLink]:
        if native_id in self._issue_by_key:
            return mapper.map_links(self._issue_by_key[native_id])
        if native_id in self._comment_by_native_id:
            comment = self._comment_by_native_id[native_id]
            return mapper.map_comment_links(comment, comment["issue_key"])
        return []

    async def get_acl_reference(self, native_id: str) -> ACLReference:
        project_key = None
        if native_id in self._issue_by_key:
            project_key = self._issue_by_key[native_id]["project_key"]
        return ACLReference(
            native_id=native_id, acl_ref={"project": project_key} if project_key else {}
        )
