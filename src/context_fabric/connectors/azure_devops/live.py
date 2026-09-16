"""Azure DevOps live-mode connector (fast-tracked ahead of Phase 19 at the
user's request, to validate the config page + rate-limit handling against
a real ADO organization).

Reuses connectors/azure_devops/mapper.py unchanged — Azure DevOps's real
REST API work-item shape (`{"id", "rev", "fields": {...}, "relations": [...],
"url"}`) is exactly what the fixture JSON was modeled on, so the same
mapper functions apply to live payloads with no translation layer of
their own.

Entity types (docs/CONNECTORS.md "Entity type selection"): which of
work_items / repos / pull_requests / wiki this connector instance
actually fetches is chosen per-connection at creation time (the UI's
"what to pull" checkboxes -> config.entity_types), not hardcoded. See
ENTITY_TYPES below for the full set and their UI labels. Git repos are
listed as lightweight containers only (id/name/default branch) — no
branch/tree/blob crawl; only Pull Requests hang off them.

Known simplifications, called out rather than hidden:
  - get_acl_reference returns {"project": <name>} — a real ADO security-
    namespace permission check is out of scope for this fast-tracked pass;
    good enough to exist structurally, not a real authorization check.
  - get_changes only reports deletions via the Recycle Bin API, scoped to
    projects already fetched this session.
  - list_changed_since (duck-typed, not part of SourceConnector) gives
    synchronization/orchestrator.py's incremental mode a real "since
    cursor" delta query for work items via System.ChangedDate — but only
    work items; repos/PRs/builds/pipelines still need a full sync to pick
    up changes.
  - Builds are not fetched at all yet (mapper.map_build exists for a
    future pass, unused here).

Every HTTP call goes through LiveConnectorBase.call_with_retry (bounded
exponential backoff + jitter, retried only for Transient/RateLimited,
honoring a Retry-After header when ADO sends one) and
raise_for_status_category (401/403 -> AuthError, 404 -> NotFound, 429 ->
RateLimited, 5xx -> Transient, other 4xx -> Permanent).
"""

from __future__ import annotations

import base64
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any, ClassVar
from urllib.parse import urlsplit, urlunsplit

import httpx
import structlog

from context_fabric.connectors.azure_devops import mapper
from context_fabric.connectors.base import DEFAULT_TIMEOUT, LiveConnectorBase
from context_fabric.domain.connector_types import (
    ACLReference,
    ChangePage,
    Page,
    SourceContainer,
    SourceContent,
    SourceLink,
    SourceObject,
)
from context_fabric.domain.errors import AuthError, NotFound, Permanent

logger = structlog.get_logger()

_API_VERSION = "7.1"

# Rolling retention window for run/execution-history entity types (builds,
# pipeline runs, test runs) — user-confirmed decision: keep recent history
# for trend questions, never accumulate unbounded run-by-run rows. Applied
# at fetch time (the API is asked only for items newer than this) rather
# than as a separate post-sync pruning pass — simplest correct
# implementation for a first pass since these entity types have no prior
# synced rows to prune yet.
_RUN_HISTORY_RETENTION_DAYS = 90

# Default cap on how many of a project's most recent builds to sync, on top
# of the days-based window above — user-reported: every build proposes a
# `relates_to` edge to its own repository (map_build_links, ADO's own
# structured `repository.id` field), so a 90-day window on an active
# pipeline can still mean 100+ near-identical PROPOSED edges swamping the
# review queue for no real new information past the most recent handful.
# Overridable per connection via config.build_retention_count (same
# pattern as entity_types/selected_containers, docs/CONNECTORS.md
# "Entity type selection").
_DEFAULT_BUILD_RETENTION_COUNT = 25


def _retention_cutoff_iso() -> str:
    return (datetime.now(UTC) - timedelta(days=_RUN_HISTORY_RETENTION_DAYS)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def _chunk(items: list[str], size: int) -> Iterator[list[str]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


def _normalize_org_url(org_url: str) -> str:
    """Strips anything beyond the organization root — a URL copied from
    the browser while inside a project (e.g.
    "https://devonrepo.visualstudio.com/DevOnHire" or
    "https://dev.azure.com/devonrepo/DevOnHire") carries the project
    name along, and every REST call here (starting with
    /_apis/projects) needs the bare org root or it 404s."""
    parts = urlsplit(org_url.strip().rstrip("/"))
    host = parts.netloc.lower()
    segments = [seg for seg in parts.path.split("/") if seg]
    if host.endswith(".visualstudio.com"):
        # Org is the subdomain — no path segment belongs here at all.
        path = ""
    elif host == "dev.azure.com":
        # Org is the one required path segment — keep only that.
        path = f"/{segments[0]}" if segments else ""
    else:
        path = parts.path.rstrip("/")
    return urlunsplit((parts.scheme, parts.netloc, path, "", ""))


def _flatten_wiki_tree(
    node: dict[str, Any], wiki_id: str, *, is_root: bool = True
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    if not is_root:
        path = node["path"]
        results.append(
            {
                "wiki_id": wiki_id,
                "path": path,
                "url": node.get("remoteUrl", ""),
                "native_id": f"{wiki_id}:{path}",
            }
        )
    for child in node.get("subPages") or []:
        results.extend(_flatten_wiki_tree(child, wiki_id, is_root=False))
    return results


def _flatten_area_tree(
    node: dict[str, Any], project: str, *, is_root: bool = True
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    if not is_root:
        path = node["path"].lstrip("\\")
        results.append(
            {
                "id": path,
                "name": node["name"],
                "project": project,
                "path": path,
                "url": node.get("url", ""),
            }
        )
    for child in node.get("children") or []:
        results.extend(_flatten_area_tree(child, project, is_root=False))
    return results


class AzureDevOpsLiveConnector(LiveConnectorBase):
    source_system = "azure_devops"

    # The "what to pull" checkboxes the UI renders for this source
    # (docs/CONNECTORS.md "Entity type selection") — key is what's stored
    # in config.entity_types, value is the UI label.
    ENTITY_TYPES: ClassVar[dict[str, str]] = {
        "work_items": "Work Items (epics/features/stories/tasks/bugs)",
        "repos": "Git Repos",
        "pull_requests": "Pull Requests",
        "wiki": "Wiki Pages",
        "builds": f"Builds (status only, last {_RUN_HISTORY_RETENTION_DAYS} days)",
        "pipelines": f"Pipelines + Runs (status only, last {_RUN_HISTORY_RETENTION_DAYS} days)",
        "environments": "Environments",
        "test_runs": f"Test Runs (aggregate pass/fail only, last {_RUN_HISTORY_RETENTION_DAYS} days)",
        "ai_assets": "AI Explorer (agents/skills/rules under .github, .claude, .cursor)",
    }

    # Which node kinds each entity type produces — synchronization/
    # orchestrator.py's generalized tombstone sweep uses this to skip
    # only the kinds whose fetch actually degraded this pass, rather than
    # skipping the whole connector's sweep over one unrelated optional
    # type erroring (real case hit in this environment: `environments`
    # 401 and `test_runs` 400 both fail on this PAT/project every run,
    # which under a whole-connector skip meant builds/PRs/work items
    # could never be pruned at all).
    ENTITY_TYPE_KINDS: ClassVar[dict[str, set[str]]] = {
        "work_items": {
            "EPIC",
            "FEATURE",
            "STORY",
            "TASK",
            "BUG",
            "WORK_ITEM",
            "TEST_CASE",
            "TEST_SUITE",
            "TEST_PLAN",
        },
        "repos": {"GIT_REPOSITORY"},
        "pull_requests": {"PULL_REQUEST"},
        "wiki": {"WIKI_PAGE"},
        "builds": {"BUILD"},
        "pipelines": {"PIPELINE"},
        "environments": {"ENVIRONMENT"},
        "test_runs": {"TEST_RUN"},
        "ai_assets": {"AI_ASSET"},
    }

    def __init__(
        self,
        org_url: str,
        *,
        pat: str,
        api_version: str = _API_VERSION,
        timeout: httpx.Timeout = DEFAULT_TIMEOUT,
        max_attempts: int = 5,
        entity_types: list[str] | None = None,
        selected_containers: list[str] | None = None,
        build_retention_count: int = _DEFAULT_BUILD_RETENTION_COUNT,
    ) -> None:
        org_url = _normalize_org_url(org_url)
        token = base64.b64encode(f":{pat}".encode()).decode("ascii")
        headers = {"Authorization": f"Basic {token}", "Content-Type": "application/json"}
        super().__init__(org_url, timeout=timeout, headers=headers, max_attempts=max_attempts)
        self._api_version = api_version
        self._entity_types = set(entity_types) if entity_types else set(self.ENTITY_TYPES)
        self._build_retention_count = build_retention_count
        # Which projects to actually sync — None means "all of them"
        # (docs/UI.md "Connectors" project picker, POST /connectors/browse
        # is what lists the choices before this is set).
        self._selected_containers = set(selected_containers) if selected_containers else None

        self._projects_raw: list[dict[str, Any]] | None = None
        self._area_paths_by_project: dict[str, list[dict[str, Any]]] = {}
        self._work_items_raw_by_id: dict[str, dict[str, Any]] = {}
        self._fetched_work_items_for_project: set[str] = set()
        self._repos_by_project: dict[str, list[dict[str, Any]]] = {}
        self._repo_by_id: dict[str, dict[str, Any]] = {}
        self._ai_assets_by_repo: dict[str, list[dict[str, Any]]] = {}
        self._pull_requests_by_repo: dict[str, list[dict[str, Any]]] = {}
        self._pull_request_by_native_id: dict[str, dict[str, Any]] = {}
        self._wikis_by_project: dict[str, list[dict[str, Any]]] = {}
        self._wiki_project_by_id: dict[str, str] = {}
        self._wiki_pages_by_wiki: dict[str, list[dict[str, Any]]] = {}
        self._wiki_page_by_native_id: dict[str, dict[str, Any]] = {}
        self._builds_by_project: dict[str, list[dict[str, Any]]] = {}
        self._build_by_native_id: dict[str, dict[str, Any]] = {}
        self._pipelines_by_project: dict[str, list[dict[str, Any]]] = {}
        self._pipeline_project_by_native_id: dict[str, str] = {}
        self._environments_by_project: dict[str, list[dict[str, Any]]] = {}
        self._test_runs_by_project: dict[str, list[dict[str, Any]]] = {}
        # native_id -> real parent native_id, for Test Case/Suite/Plan
        # nodes — ADO's actual Plan->Suite->Case structure lives in a
        # separate Test Management API, not System.Parent, so this
        # overrides map_work_item's default (area-path/project) parent
        # once fetched. Empty until _ensure_test_hierarchy succeeds.
        self._test_hierarchy_override: dict[str, str] = {}
        self._test_hierarchy_fetched: set[str] = set()

    # -- low-level HTTP -----------------------------------------------

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        async def do_call() -> httpx.Response:
            response = await self.client.request(method, path, **kwargs)
            self.raise_for_status_category(response)
            return response

        response = await self.call_with_retry(do_call)
        result: dict[str, Any] = response.json()
        return result

    # -- discovery / hierarchy ------------------------------------------

    async def discover_containers(self) -> list[SourceContainer]:
        data = await self._request("GET", f"/_apis/projects?api-version={self._api_version}")
        all_projects = data.get("value", [])
        if self._selected_containers is not None:
            all_projects = [p for p in all_projects if p["name"] in self._selected_containers]
        self._projects_raw = all_projects
        return [
            mapper.map_project(
                {
                    "id": p["name"],
                    "name": p["name"],
                    "description": p.get("description", ""),
                    "url": p.get("url", ""),
                }
            )
            for p in self._projects_raw
        ]

    async def _project_names(self) -> set[str]:
        if self._projects_raw is None:
            await self.discover_containers()
        return {p["name"] for p in (self._projects_raw or [])}

    async def _get_area_paths(self, project: str) -> list[dict[str, Any]]:
        if project not in self._area_paths_by_project:
            tree = await self._request(
                "GET",
                f"/{project}/_apis/wit/classificationnodes/Areas"
                f"?$depth=20&api-version={self._api_version}",
            )
            self._area_paths_by_project[project] = _flatten_area_tree(tree, project)
        return self._area_paths_by_project[project]

    async def _ensure_work_items_fetched(self, project: str) -> None:
        if project in self._fetched_work_items_for_project:
            return
        wiql = {
            "query": f"SELECT [System.Id] FROM WorkItems WHERE [System.TeamProject] = '{project}'"
        }
        result = await self._request(
            "POST", f"/{project}/_apis/wit/wiql?api-version={self._api_version}", json=wiql
        )
        ids = [str(wi["id"]) for wi in result.get("workItems", [])]
        for batch in _chunk(ids, 200):
            # "fields" and "$expand" are mutually exclusive on this ADO
            # endpoint (a 400 "Validation Failed" if both are set) —
            # $expand=relations returns every field anyway (a superset
            # of _WORK_ITEM_FIELDS), so map_work_item still finds what
            # it needs.
            batch_body = {
                "ids": [int(i) for i in batch],
                "$expand": "relations",
            }
            batch_result = await self._request(
                "POST",
                f"/_apis/wit/workitemsbatch?api-version={self._api_version}",
                json=batch_body,
            )
            for wi in batch_result.get("value", []):
                self._work_items_raw_by_id[str(wi["id"])] = wi
        self._fetched_work_items_for_project.add(project)

    async def _ensure_repos(self, project: str) -> list[dict[str, Any]]:
        if project not in self._repos_by_project:
            data = await self._request(
                "GET", f"/{project}/_apis/git/repositories?api-version={self._api_version}"
            )
            repos = data.get("value", [])
            self._repos_by_project[project] = repos
            for r in repos:
                self._repo_by_id[r["id"]] = r
        return self._repos_by_project[project]

    async def _ensure_pull_requests(self, repo_id: str) -> list[dict[str, Any]]:
        if repo_id not in self._pull_requests_by_repo:
            data = await self._request(
                "GET",
                f"/_apis/git/repositories/{repo_id}/pullrequests"
                f"?searchCriteria.status=all&api-version={self._api_version}",
            )
            prs = data.get("value", [])
            self._pull_requests_by_repo[repo_id] = prs
            for pr in prs:
                self._pull_request_by_native_id[f"PR-{pr['pullRequestId']}"] = pr
        return self._pull_requests_by_repo[repo_id]

    async def _ensure_ai_assets(self, repo_id: str) -> list[dict[str, Any]]:
        """AI Explorer entries — mirrors GitHubLiveConnector._ensure_ai_assets,
        using ADO's Git Items API (a single recursive tree listing, then a
        per-file content fetch for whatever classifies as an AI asset)
        instead of GitHub's git-trees + contents API. Its own lightweight
        fetch, not reused from anywhere else in this connector — no other
        entity type needs a full repo tree listing, and ADO repos are
        never crawled for raw code content here (same scope limit as
        map_git_repository's own docstring)."""
        if repo_id in self._ai_assets_by_repo:
            return self._ai_assets_by_repo[repo_id]

        repo = self._repo_by_id.get(repo_id)
        project = (
            repo["project"]["name"]
            if repo is not None and isinstance(repo.get("project"), dict)
            else ""
        )
        try:
            tree_data = await self._request(
                "GET",
                f"/{project}/_apis/git/repositories/{repo_id}/items",
                params={"recursionLevel": "Full", "api-version": self._api_version},
            )
        except (AuthError, NotFound, Permanent) as exc:
            logger.warning("azure_devops.ai_assets_unavailable", repo=repo_id, error=str(exc))
            self._mark_degraded("ai_assets", str(exc))
            self._ai_assets_by_repo[repo_id] = []
            return []

        assets: list[dict[str, Any]] = []
        for entry in tree_data.get("value", []):
            if entry.get("isFolder"):
                continue
            # ADO item paths are rooted ("/.github/agents/reviewer.md") —
            # classify_ai_asset_path expects the same unrooted shape
            # GitHub's tree API already returns.
            path = entry["path"].lstrip("/")
            classified = mapper.classify_ai_asset_path(path)
            if classified is None:
                continue
            vendor, asset_type = classified
            try:
                content_data = await self._request(
                    "GET",
                    f"/{project}/_apis/git/repositories/{repo_id}/items",
                    params={
                        "path": entry["path"],
                        "includeContent": "true",
                        "api-version": self._api_version,
                    },
                )
            except (AuthError, NotFound, Permanent) as exc:
                logger.warning(
                    "azure_devops.ai_asset_content_unavailable",
                    repo=repo_id,
                    path=path,
                    error=str(exc),
                )
                continue
            text = content_data.get("content", "")
            fallback_name = path.rsplit("/", 1)[-1].rsplit(".", 1)[0]
            name, description = mapper.parse_ai_asset_description(text, fallback_name=fallback_name)
            assets.append(
                {
                    "path": path,
                    "vendor": vendor,
                    "asset_type": asset_type,
                    "name": name,
                    "description": description,
                }
            )
        self._ai_assets_by_repo[repo_id] = assets
        return assets

    async def _ensure_wikis(self, project: str) -> list[dict[str, Any]]:
        if project not in self._wikis_by_project:
            data = await self._request(
                "GET", f"/{project}/_apis/wiki/wikis?api-version={self._api_version}"
            )
            wikis = data.get("value", [])
            self._wikis_by_project[project] = wikis
            for w in wikis:
                self._wiki_project_by_id[w["id"]] = project
        return self._wikis_by_project[project]

    async def _ensure_wiki_pages(self, wiki_id: str, project: str) -> list[dict[str, Any]]:
        if wiki_id not in self._wiki_pages_by_wiki:
            tree = await self._request(
                "GET",
                f"/{project}/_apis/wiki/wikis/{wiki_id}/pages",
                params={"path": "/", "recursionLevel": "full", "api-version": self._api_version},
            )
            flattened = _flatten_wiki_tree(tree, wiki_id)
            self._wiki_pages_by_wiki[wiki_id] = flattened
            for p in flattened:
                self._wiki_page_by_native_id[p["native_id"]] = p
        return self._wiki_pages_by_wiki[wiki_id]

    async def _ensure_builds(self, project: str) -> list[dict[str, Any]]:
        if project not in self._builds_by_project:
            try:
                data = await self._request(
                    "GET",
                    f"/{project}/_apis/build/builds",
                    params={
                        "minTime": _retention_cutoff_iso(),
                        "queryOrder": "queuedTimeDescending",
                        "$top": self._build_retention_count,
                        "api-version": self._api_version,
                    },
                )
            except (AuthError, NotFound, Permanent) as exc:
                # Real, encountered case: a PAT scoped for work items/repos
                # can lack the "Build (Read)" scope — optional entity type,
                # so this project's sync degrades gracefully instead of
                # failing entirely (docs/CONNECTORS.md "Entity type
                # selection" — each type is independently best-effort).
                logger.warning("azure_devops.builds_unavailable", project=project, error=str(exc))
                self._mark_degraded("builds", str(exc))
                self._builds_by_project[project] = []
                return self._builds_by_project[project]
            builds = data.get("value", [])
            self._builds_by_project[project] = builds
            for b in builds:
                self._build_by_native_id[f"BUILD-{b['id']}"] = b
        return self._builds_by_project[project]

    async def _ensure_pipelines(self, project: str) -> list[dict[str, Any]]:
        if project not in self._pipelines_by_project:
            try:
                data = await self._request(
                    "GET",
                    f"/{project}/_apis/pipelines",
                    params={"api-version": self._api_version},
                )
            except (AuthError, NotFound, Permanent) as exc:
                logger.warning(
                    "azure_devops.pipelines_unavailable", project=project, error=str(exc)
                )
                self._mark_degraded("pipelines", str(exc))
                self._pipelines_by_project[project] = []
                return self._pipelines_by_project[project]
            pipelines = data.get("value", [])
            self._pipelines_by_project[project] = pipelines
            for p in pipelines:
                self._pipeline_project_by_native_id[f"PIPELINE-{p['id']}"] = project
        return self._pipelines_by_project[project]

    async def _ensure_environments(self, project: str) -> list[dict[str, Any]]:
        if project not in self._environments_by_project:
            try:
                data = await self._request(
                    "GET",
                    f"/{project}/_apis/distributedtask/environments",
                    params={"api-version": "7.1-preview.1"},
                )
            except (AuthError, NotFound, Permanent) as exc:
                logger.warning(
                    "azure_devops.environments_unavailable", project=project, error=str(exc)
                )
                self._mark_degraded("environments", str(exc))
                self._environments_by_project[project] = []
                return self._environments_by_project[project]
            self._environments_by_project[project] = data.get("value", [])
        return self._environments_by_project[project]

    async def _ensure_test_runs(self, project: str) -> list[dict[str, Any]]:
        if project not in self._test_runs_by_project:
            try:
                data = await self._request(
                    "GET",
                    f"/{project}/_apis/test/runs",
                    params={
                        "minLastUpdatedDate": _retention_cutoff_iso(),
                        "maxLastUpdatedDate": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "api-version": self._api_version,
                    },
                )
            except (AuthError, NotFound, Permanent) as exc:
                logger.warning(
                    "azure_devops.test_runs_unavailable", project=project, error=str(exc)
                )
                self._mark_degraded("test_runs", str(exc))
                self._test_runs_by_project[project] = []
                return self._test_runs_by_project[project]
            self._test_runs_by_project[project] = data.get("value", [])
        return self._test_runs_by_project[project]

    def _parse_wiki_native_id(self, parent_id: str) -> tuple[str | None, str | None]:
        if ":" not in parent_id:
            return None, None
        wiki_id, _, path = parent_id.partition(":")
        if wiki_id not in self._wiki_project_by_id:
            return None, None
        return wiki_id, path

    async def _ensure_test_hierarchy(self, project: str) -> None:
        """ADO's real Test Plan -> Test Suite -> Test Case structure —
        a genuinely separate, built-in API (Test Management, not the
        generic work-item System.Parent field map_work_item already
        reads), which every Test Case/Suite/Plan work item in this
        project was found (via a real user report) to be missing —
        they were all attaching flat to the project instead of their
        real plan/suite tree. Best-effort: the PAT used to build this
        needed a scope ("Test Management: Read") this connection's own
        token didn't have (confirmed via a real 403), so this degrades
        gracefully — same pattern as _ensure_environments/_ensure_test_runs
        — rather than failing the whole sync over an optional refinement.
        Untested against a real success response for the same reason;
        built from Microsoft's documented Test Plan REST API shape."""
        if project in self._test_hierarchy_fetched:
            return
        self._test_hierarchy_fetched.add(project)
        try:
            plans = await self._request(
                "GET", f"/{project}/_apis/testplan/plans", params={"api-version": "7.1"}
            )
            for plan in plans.get("value", []):
                plan_id = str(plan["id"])
                suites = await self._request(
                    "GET",
                    f"/{project}/_apis/testplan/Plans/{plan_id}/suites",
                    params={"api-version": "7.1"},
                )
                for suite in suites.get("value", []):
                    suite_id = str(suite["id"])
                    parent_suite = suite.get("parentSuite")
                    if parent_suite and str(parent_suite.get("id")) != suite_id:
                        self._test_hierarchy_override[suite_id] = str(parent_suite["id"])
                    else:
                        self._test_hierarchy_override[suite_id] = plan_id

                    cases = await self._request(
                        "GET",
                        f"/{project}/_apis/testplan/Plans/{plan_id}/Suites/{suite_id}/TestCase",
                        params={"api-version": "7.1"},
                    )
                    for entry in cases.get("value", []):
                        case_ref = entry.get("testCase") or entry.get("workItem")
                        if case_ref and case_ref.get("id"):
                            self._test_hierarchy_override[str(case_ref["id"])] = suite_id
        except (AuthError, NotFound, Permanent) as exc:
            logger.warning(
                "azure_devops.test_hierarchy_unavailable", project=project, error=str(exc)
            )

    def _effective_parent(self, mapped: SourceObject) -> str | None:
        return self._test_hierarchy_override.get(mapped.native_id, mapped.parent_native_id)

    async def list_children(self, parent_id: str, cursor: str | None = None) -> Page[SourceObject]:
        project_names = await self._project_names()

        if parent_id in project_names:
            items: list[SourceObject] = []
            if "work_items" in self._entity_types:
                area_paths = await self._get_area_paths(parent_id)
                await self._ensure_work_items_fetched(parent_id)
                await self._ensure_test_hierarchy(parent_id)
                items += [mapper.map_area_path(a) for a in area_paths]
                # Work items sitting directly in the project's default
                # area (AreaPath == the bare project name, no sub-path —
                # the common case for a project that hasn't carved out
                # custom area paths) attach to the project itself, not
                # to any AREA_PATH node — _flatten_area_tree never
                # returns the root, so this is their only way in.
                items += [
                    mapped
                    for raw in self._work_items_raw_by_id.values()
                    if self._effective_parent(mapped := mapper.map_work_item(raw)) == parent_id
                ]
            # Pull Requests hang off Git Repos in this connector's native
            # hierarchy, so a repo container must be synced whenever
            # either "repos" or "pull_requests" is selected — otherwise
            # the traversal never reaches list_children(repo_id) and PRs
            # go undiscovered even though the entity type is on.
            if "repos" in self._entity_types or "pull_requests" in self._entity_types:
                repos = await self._ensure_repos(parent_id)
                items += [
                    mapper.map_git_repository(
                        {
                            "id": r["id"],
                            "name": r["name"],
                            "project": parent_id,
                            "defaultBranch": r.get("defaultBranch", ""),
                            "url": r.get("webUrl", r.get("url", "")),
                        }
                    )
                    for r in repos
                ]
            if "wiki" in self._entity_types:
                wikis = await self._ensure_wikis(parent_id)
                items += [
                    mapper.map_wiki_page(
                        {"wiki_id": w["id"], "path": "/", "url": w.get("remoteUrl", "")}
                    )
                    for w in wikis
                ]
            # Builds are Pipeline Runs (see map_build's docstring), always
            # parented under a PIPELINE node — same coupling as Pull
            # Requests requiring Git Repos above, so the PIPELINE
            # container is synced whenever either flag is on, or the walk
            # never reaches list_children(pipeline_id) and builds go
            # undiscovered even with "builds" enabled.
            if "pipelines" in self._entity_types or "builds" in self._entity_types:
                pipelines = await self._ensure_pipelines(parent_id)
                items += [mapper.map_pipeline(p, project=parent_id) for p in pipelines]
            if "environments" in self._entity_types:
                environments = await self._ensure_environments(parent_id)
                items += [mapper.map_environment(e, project=parent_id) for e in environments]
            if "test_runs" in self._entity_types:
                test_runs = await self._ensure_test_runs(parent_id)
                items += [mapper.map_test_run(t, project=parent_id) for t in test_runs]
            return Page(items=items, next_cursor=None)

        if parent_id in self._repo_by_id:
            items = []
            if "pull_requests" in self._entity_types:
                prs = await self._ensure_pull_requests(parent_id)
                items += [mapper.map_pull_request(pr) for pr in prs]
            if "ai_assets" in self._entity_types:
                assets = await self._ensure_ai_assets(parent_id)
                items += [
                    mapper.map_ai_asset(
                        parent_id,
                        a["path"],
                        vendor=a["vendor"],
                        asset_type=a["asset_type"],
                        name=a["name"],
                        description=a["description"],
                    )
                    for a in assets
                ]
            return Page(items=items, next_cursor=None)

        if parent_id in self._pipeline_project_by_native_id:
            if "builds" not in self._entity_types:
                return Page(items=[], next_cursor=None)
            project = self._pipeline_project_by_native_id[parent_id]
            builds = await self._ensure_builds(project)
            children = [
                mapper.map_build(b)
                for b in builds
                if f"PIPELINE-{b['definition']['id']}" == parent_id
            ]
            return Page(items=children, next_cursor=None)

        wiki_id, _wiki_path = self._parse_wiki_native_id(parent_id)
        if wiki_id is not None:
            project = self._wiki_project_by_id[wiki_id]
            pages = await self._ensure_wiki_pages(wiki_id, project)
            children = [
                mapped
                for raw in pages
                if (mapped := mapper.map_wiki_page(raw)).parent_native_id == parent_id
            ]
            return Page(items=children, next_cursor=None)

        # An area-path native_id is "Project\...\Area" — the project name
        # is always its first segment, so we can find/ensure its work
        # items are fetched without a separate reverse index.
        maybe_project = parent_id.split("\\", 1)[0]
        if "work_items" in self._entity_types and maybe_project in project_names:
            await self._ensure_work_items_fetched(maybe_project)

        children = [
            mapped
            for raw in self._work_items_raw_by_id.values()
            if self._effective_parent(mapped := mapper.map_work_item(raw)) == parent_id
        ]
        return Page(items=children, next_cursor=None)

    # -- single-object lookups -------------------------------------------

    async def get_object(self, native_id: str) -> SourceObject:
        if native_id in self._work_items_raw_by_id:
            return mapper.map_work_item(self._work_items_raw_by_id[native_id])

        for _project, area_paths in self._area_paths_by_project.items():
            for a in area_paths:
                if a["id"] == native_id:
                    return mapper.map_area_path(a)

        if native_id in self._repo_by_id:
            r = self._repo_by_id[native_id]
            project = r["project"]["name"] if isinstance(r.get("project"), dict) else ""
            return mapper.map_git_repository(
                {
                    "id": r["id"],
                    "name": r["name"],
                    "project": project,
                    "defaultBranch": r.get("defaultBranch", ""),
                    "url": r.get("webUrl", r.get("url", "")),
                }
            )

        if native_id in self._pull_request_by_native_id:
            return mapper.map_pull_request(self._pull_request_by_native_id[native_id])

        if native_id in self._wiki_page_by_native_id:
            return mapper.map_wiki_page(self._wiki_page_by_native_id[native_id])

        if native_id.isdigit():
            data = await self._request(
                "GET",
                f"/_apis/wit/workitems/{native_id}"
                f"?$expand=relations&api-version={self._api_version}",
            )
            self._work_items_raw_by_id[native_id] = data
            return mapper.map_work_item(data)

        raise NotFound(
            f"no Azure DevOps object with native_id={native_id!r}", source_system=self.source_system
        )

    async def get_content(self, native_id: str, version: str | None = None) -> SourceContent:
        if native_id in self._wiki_page_by_native_id:
            page = self._wiki_page_by_native_id[native_id]
            project = self._wiki_project_by_id[page["wiki_id"]]
            data = await self._request(
                "GET",
                f"/{project}/_apis/wiki/wikis/{page['wiki_id']}/pages",
                params={
                    "path": page["path"],
                    "includeContent": "true",
                    "api-version": self._api_version,
                },
            )
            return mapper.map_wiki_page_content(
                native_id, {"content": data.get("content", ""), "url": page.get("url", "")}
            )

        # AI assets (agent/skill/rule definitions) — same on-demand fetch
        # as GitHubLiveConnector.get_content's ai_asset branch: a caller
        # discovers "this repo has a reviewer agent" through the catalog,
        # then fetches the definition here. Repo id is a GUID, so
        # `native_id` alone doesn't say which project it's under — looked
        # up via `_repo_by_id`, populated whenever `_ensure_repos` (or
        # `_ensure_ai_assets`, itself dependent on it) has already run for
        # this connection, which sync always does before content fetches.
        ai_asset = mapper.parse_ai_asset_ref(native_id)
        if ai_asset is not None:
            repo_id, asset_path = ai_asset
            repo = self._repo_by_id.get(repo_id)
            project = (
                repo["project"]["name"]
                if repo is not None and isinstance(repo.get("project"), dict)
                else ""
            )
            data = await self._request(
                "GET",
                f"/{project}/_apis/git/repositories/{repo_id}/items",
                params={
                    "path": f"/{asset_path}",
                    "includeContent": "true",
                    "api-version": self._api_version,
                },
            )
            return mapper.map_wiki_page_content(
                native_id, {"content": data.get("content", ""), "url": data.get("url", "")}
            )

        if native_id not in self._work_items_raw_by_id:
            await self.get_object(native_id)
        raw = self._work_items_raw_by_id.get(native_id)
        if raw is None:
            raise NotFound(
                f"no content for native_id={native_id!r}", source_system=self.source_system
            )
        return mapper.map_content(native_id, raw)

    # -- change feed / links / acl ----------------------------------------

    async def get_changes(self, cursor: str | None = None) -> ChangePage:
        """Deletions only, via the Recycle Bin API, scoped to projects
        already fetched this session — see module docstring."""
        items: list[SourceObject] = []
        for project in self._fetched_work_items_for_project:
            data = await self._request(
                "GET", f"/{project}/_apis/wit/recyclebin?api-version={self._api_version}"
            )
            for entry in data.get("value", []):
                native_id = str(entry["id"])
                kind = mapper.WORK_ITEM_TYPE_TO_KIND.get(entry.get("workItemType", ""), "WORK_ITEM")
                items.append(mapper.map_tombstone(native_id, kind))
        return ChangePage(items=items, next_cursor=None, has_more=False)

    async def list_changed_since(self, cursor: str | None) -> Page[SourceObject]:
        """Work items changed since `cursor` (an ISO 8601 timestamp), across
        every project this connection can see — the incremental
        counterpart to `_ensure_work_items_fetched`'s full-project WIQL
        query. Not part of the `SourceConnector` protocol — duck-typed and
        checked with `hasattr` by `synchronization/orchestrator.py`'s
        incremental sync mode, so a connector that doesn't implement it
        (every other one, today) is a graceful full-sync fallback rather
        than a broken interface.

        Reference implementation, not full incremental coverage: scoped to
        work items only, the dominant volume here (628 of ~770 nodes at
        last count) and the one entity type ADO's own `System.ChangedDate`
        field makes a clean delta query for. Repos/PRs/builds/pipelines
        still need a full sync to pick up changes — a real limitation,
        named here rather than silently assumed away.

        `cursor is None` (first incremental run) looks back 24h rather
        than fetching everything — an unbounded "since the beginning of
        time" query is just a full sync with extra steps; the first
        incremental pass genuinely has nothing more recent to report until
        a full sync has run at least once."""
        if "work_items" not in self._entity_types:
            return Page(items=[], next_cursor=cursor)

        since = cursor or (datetime.now(UTC) - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        projects = await self._project_names()
        if self._selected_containers is not None:
            projects &= self._selected_containers

        items: list[SourceObject] = []
        for project in sorted(projects):
            wiql = {
                "query": (
                    "SELECT [System.Id] FROM WorkItems "
                    f"WHERE [System.TeamProject] = '{project}' "
                    f"AND [System.ChangedDate] > '{since}' "
                    "ORDER BY [System.ChangedDate] ASC"
                )
            }
            try:
                result = await self._request(
                    "POST",
                    # timePrecision=true is required, not optional decor —
                    # confirmed live: without it ADO rejects any WIQL date
                    # comparison carrying a time-of-day component at all
                    # ("You cannot supply a time with the date when running
                    # a query using date precision"), which is exactly the
                    # ChangedDate literal below. Its default (date-only
                    # precision) would silently coarsen a same-day
                    # incremental cursor to midnight, re-matching every
                    # item changed earlier the same day on every pass.
                    f"/{project}/_apis/wit/wiql"
                    f"?api-version={self._api_version}&timePrecision=true",
                    json=wiql,
                )
            except (AuthError, NotFound, Permanent) as exc:
                # Same optional-entity-type tolerance as everywhere else in
                # this connector — one project's permission hiccup must
                # not take down the whole incremental pass.
                logger.warning(
                    "azure_devops.incremental_fetch_failed", project=project, error=str(exc)
                )
                continue

            ids = [str(wi["id"]) for wi in result.get("workItems", [])]
            for batch in _chunk(ids, 200):
                batch_result = await self._request(
                    "POST",
                    f"/_apis/wit/workitemsbatch?api-version={self._api_version}",
                    json={"ids": [int(i) for i in batch], "$expand": "relations"},
                )
                for wi in batch_result.get("value", []):
                    self._work_items_raw_by_id[str(wi["id"])] = wi
                    items.append(mapper.map_work_item(wi))

        # The watermark for next time is "now," not the latest item's own
        # ChangedDate — using an item's timestamp would re-fetch it forever
        # (it is not strictly greater than itself), and clock skew between
        # us and ADO is smaller risk than that.
        new_cursor = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        return Page(items=items, next_cursor=new_cursor)

    async def get_links(self, native_id: str) -> list[SourceLink]:
        if native_id in self._work_items_raw_by_id:
            return mapper.map_links(self._work_items_raw_by_id[native_id])
        if native_id in self._build_by_native_id:
            return mapper.map_build_links(self._build_by_native_id[native_id])
        # Previously missing entirely — a PR native_id fell straight
        # through to `return []`, so no ADO pull request's title, branch
        # name, or description was ever scanned for a cross-reference.
        if native_id in self._pull_request_by_native_id:
            return mapper.map_pull_request_links(self._pull_request_by_native_id[native_id])
        return []

    async def get_acl_reference(self, native_id: str) -> ACLReference:
        raw = self._work_items_raw_by_id.get(native_id)
        project = None
        if raw is not None:
            area_path = raw["fields"].get("System.AreaPath", "")
            project = area_path.split("\\", 1)[0] if area_path else None
        if project is None:
            for proj, area_paths in self._area_paths_by_project.items():
                if any(a["id"] == native_id for a in area_paths):
                    project = proj
                    break
        return ACLReference(native_id=native_id, acl_ref={"project": project} if project else {})
