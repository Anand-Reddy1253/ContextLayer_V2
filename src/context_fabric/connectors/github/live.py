"""GitHub live-mode connector (fast-tracked ahead of Phase 19 alongside
Azure DevOps's, at the user's request).

Reuses connectors/github/mapper.py unchanged — same rationale as
connectors/azure_devops/live.py: the fixture JSON shapes were modeled on
the real GitHub REST API's own response shapes.

Entity types (docs/CONNECTORS.md "Entity type selection"): which of
issues / pull_requests / projects this connector instance fetches is
chosen per-connection at creation time (config.entity_types) — see
ENTITY_TYPES below. Repos themselves are always listed (as lightweight
containers so Issues/PRs/Projects have somewhere to attach); the deep
branch/tree/blob/commit code crawl this connector also knows how to do
is gated behind an internal "code" entity type that ENTITY_TYPES
deliberately does not advertise, so the UI never offers it and no
connection fetches raw code content by default.

Known simplifications:
  - get_acl_reference returns {"org": ..., "repo": ...} — no real GitHub
    permission-API check.
  - Actions runs are not fetched by list_children (matching the fixture
    connector's own scope) — only reachable via get_object if ever
    requested directly, which live mode doesn't currently do.
  - Projects (v2) items are mapped as lightweight pointers (content
    type + URL) via GraphQL — not a full copy of the linked Issue/PR's
    own fields, which are already available via the issues/pull_requests
    entity types.

Both organization and personal-account logins are supported throughout
(repos, issues, PRs, Projects v2) — _ensure_account_kind tries
/orgs/{login} first and falls back to /users/{login}, since a bare
login string never says which one it is on its own.

Private repos on a personal account (config.repo_visibility, default
"all"): GitHub's /users/{login}/repos only ever returns PUBLIC repos for
that user — even when {login} is the token's own account. Getting
private ones too requires the token-relative /user/repos endpoint
instead (no username in the path), which _repos_request switches to
once it confirms (via GET /user) that the login being browsed is the
token's own. Org repo listing doesn't have this gap — /orgs/{org}/repos
already includes every repo the token can see.

Every call goes through LiveConnectorBase.call_with_retry and
raise_for_status_category, so GitHub's own rate limiting (403 with an
X-RateLimit-Remaining: 0 header, or a plain 429) is handled the same way
as ADO's — retried with backoff, honoring Retry-After / rate-limit reset
when GitHub sends one.
"""

from __future__ import annotations

import base64
import posixpath
import time
from typing import Any, ClassVar

import httpx
import structlog

from context_fabric.connectors.base import DEFAULT_TIMEOUT, LiveConnectorBase
from context_fabric.connectors.github import mapper
from context_fabric.domain.connector_types import (
    ACLReference,
    ChangePage,
    Page,
    SourceContainer,
    SourceContent,
    SourceLink,
    SourceObject,
)
from context_fabric.domain.errors import AuthError, NotFound, Permanent, RateLimited

logger = structlog.get_logger()

_API_BASE = "https://api.github.com"


def _normalize_login(org: str) -> str:
    """Strips a pasted GitHub URL down to the bare login — a URL copied
    from the browser (org page, or worse, a specific repo page like
    "https://github.com/octocat/Hello-World") carries the host and any
    repo path along, and every REST call here (starting with
    /orgs/{login} or /users/{login}) needs just the login or 404s."""
    org = org.strip().rstrip("/")
    if "github.com/" in org:
        org = org.split("github.com/", 1)[1]
    return org.split("/", 1)[0]


# Projects (v2) has no REST equivalent — owner-scoped boards plus a
# shallow read of each item's linked content, enough to identify what it
# points at (docs/CONNECTORS.md "Entity type selection"). GitHub's
# GraphQL schema exposes projectsV2 under both Query.organization and
# Query.user (both implement ProjectV2Owner) — "__OWNER_FIELD__" is
# swapped for whichever this account actually is (plain string replace,
# not str.format, since escaping every other brace in this query for
# .format would be error-prone), chosen once via _ensure_account_kind
# since a bare login string doesn't say which.
_PROJECTS_V2_QUERY_TEMPLATE = """
query($org: String!, $after: String) {
  __OWNER_FIELD__(login: $org) {
    projectsV2(first: 20, after: $after) {
      pageInfo { hasNextPage endCursor }
      nodes {
        id
        number
        title
        url
        items(first: 100) {
          nodes {
            id
            content {
              __typename
              ... on Issue { title url }
              ... on PullRequest { title url }
              ... on DraftIssue { title }
            }
          }
        }
      }
    }
  }
}
"""


class GitHubLiveConnector(LiveConnectorBase):
    source_system = "github"

    # The "what to pull" checkboxes the UI renders for this source
    # (docs/CONNECTORS.md "Entity type selection") — key is what's stored
    # in config.entity_types, value is the UI label. "code" deliberately
    # isn't listed here — see module docstring.
    ENTITY_TYPES: ClassVar[dict[str, str]] = {
        "issues": "Issues",
        "pull_requests": "Pull Requests",
        "projects": "Projects (v2)",
        "ai_assets": "AI Explorer (agents/skills/rules under .github, .claude, .cursor)",
    }

    # See AzureDevOpsLiveConnector.ENTITY_TYPE_KINDS — same purpose: lets
    # the tombstone sweep skip only the degraded entity type's own kinds
    # instead of this connector's whole sweep.
    ENTITY_TYPE_KINDS: ClassVar[dict[str, set[str]]] = {
        "issues": {"ISSUE"},
        "pull_requests": {"PULL_REQUEST"},
        "projects": {"PROJECT_BOARD", "PROJECT_ITEM"},
        "ai_assets": {"AI_ASSET"},
    }

    def __init__(
        self,
        org: str,
        *,
        token: str,
        timeout: httpx.Timeout = DEFAULT_TIMEOUT,
        max_attempts: int = 5,
        entity_types: list[str] | None = None,
        selected_containers: list[str] | None = None,
        repo_visibility: str = "all",
    ) -> None:
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        super().__init__(_API_BASE, timeout=timeout, headers=headers, max_attempts=max_attempts)
        self._org = _normalize_login(org)
        self._entity_types = set(entity_types) if entity_types else set(self.ENTITY_TYPES)
        # Which repos to actually sync (full_name, e.g. "acme/identity") —
        # None means "all of them" (docs/UI.md "Connectors" repo picker,
        # POST /connectors/browse lists the choices before this is set).
        self._selected_containers = set(selected_containers) if selected_containers else None
        # "all" | "public" | "private" — only meaningful on the /user/repos
        # path below (a personal account browsing itself); org repo
        # listing already includes private repos the PAT can see with no
        # extra parameter needed.
        self._repo_visibility = repo_visibility
        # GitHub's REST API has separate namespaces for organizations
        # (/orgs/{login}) and personal accounts (/users/{login}) — a repo
        # owner isn't necessarily an org, so this is detected once
        # (discover_containers) rather than assumed.
        self._account_kind: str | None = None
        # The token's own login (GET /user) — /users/{login}/repos only
        # ever returns PUBLIC repos for that user, even when {login} is
        # the token's own account; /user/repos (no username, resolved
        # from the token itself) is the endpoint that includes private
        # repos too, so this decides which one to call.
        self._authenticated_login: str | None = None

        self._repos_raw: list[dict[str, Any]] | None = None
        self._branches_by_repo: dict[str, list[dict[str, Any]]] = {}
        self._tree_by_repo_branch: dict[str, list[dict[str, Any]]] = {}
        self._commits_by_repo: dict[str, list[dict[str, Any]]] = {}
        self._commit_by_sha: dict[str, dict[str, Any]] = {}
        self._issues_by_repo: dict[str, list[dict[str, Any]]] = {}
        self._issue_by_native_id: dict[str, dict[str, Any]] = {}
        self._pull_requests_by_repo: dict[str, list[dict[str, Any]]] = {}
        self._pull_request_by_native_id: dict[str, dict[str, Any]] = {}
        self._projects_v2_raw: list[dict[str, Any]] | None = None
        self._project_v2_by_native_id: dict[str, dict[str, Any]] = {}
        self._ai_assets_by_repo: dict[str, list[dict[str, Any]]] = {}
        self._project_v2_items_by_native_id: dict[str, dict[str, Any]] = {}

    # -- low-level HTTP -----------------------------------------------

    def raise_for_status_category(self, response: httpx.Response) -> None:
        # GitHub signals rate limiting as 403 with X-RateLimit-Remaining:
        # 0 (not always a plain 429) — translate that specific case to
        # RateLimited before falling back to the generic mapping.
        if response.status_code == 403 and response.headers.get("X-RateLimit-Remaining") == "0":
            reset = response.headers.get("X-RateLimit-Reset")
            retry_after = None
            if reset:
                retry_after = max(0.0, float(reset) - time.time())
            raise RateLimited(
                f"GitHub rate limit exhausted (resets at {reset})",
                source_system=self.source_system,
                retry_after_seconds=retry_after,
            )
        super().raise_for_status_category(response)

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        async def do_call() -> httpx.Response:
            response = await self.client.request(method, path, **kwargs)
            self.raise_for_status_category(response)
            return response

        response = await self.call_with_retry(do_call)
        return response.json()

    async def _paginated(self, path: str, **params: Any) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        page = 1
        while True:
            page_params = {**params, "per_page": 100, "page": page}
            data = await self._request("GET", path, params=page_params)
            if not data:
                break
            results.extend(data)
            if len(data) < 100:
                break
            page += 1
        return results

    async def _graphql(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        async def do_call() -> httpx.Response:
            body = {"query": query, "variables": variables}
            response = await self.client.post("/graphql", json=body)
            self.raise_for_status_category(response)
            return response

        response = await self.call_with_retry(do_call)
        payload = response.json()
        if payload.get("errors") and not payload.get("data"):
            # No data at all (e.g. the login itself doesn't resolve) —
            # nothing usable came back, so this is a hard failure.
            raise Permanent(
                f"GitHub GraphQL error: {payload['errors']}", source_system=self.source_system
            )
        if payload.get("errors"):
            # GraphQL allows partial success: some fields resolved, others
            # came back null with an error (commonly a fine-grained PAT
            # missing the "Projects" permission specifically — a separate
            # scope from repo access). Log and keep going with whatever
            # did resolve, same as an empty/unresolved REST result
            # elsewhere — one inaccessible entity type shouldn't fail the
            # whole sync.
            logger.warning(
                "github.graphql_partial_error",
                source_system=self.source_system,
                errors=payload["errors"],
            )
        result: dict[str, Any] = payload.get("data") or {}
        return result

    # -- discovery / hierarchy ------------------------------------------

    async def _ensure_account_kind(self) -> str:
        """Tries /orgs/{login} first (the common case); falls back to
        /users/{login} for a personal account rather than failing, since
        nothing about a bare login string says which one it is."""
        if self._account_kind is None:
            try:
                await self._request("GET", f"/orgs/{self._org}")
                self._account_kind = "orgs"
            except NotFound:
                await self._request("GET", f"/users/{self._org}")
                self._account_kind = "users"
        return self._account_kind

    async def _ensure_authenticated_login(self) -> str:
        if self._authenticated_login is None:
            try:
                data = await self._request("GET", "/user")
                self._authenticated_login = data.get("login", "")
            except (NotFound, Permanent):
                # A fine-grained PAT scoped to specific repos (rather
                # than "all repositories") can 403 on /user — treat as
                # "can't tell", which just means the /user/repos
                # shortcut below never kicks in.
                self._authenticated_login = ""
        return self._authenticated_login

    async def _repos_request(self) -> list[dict[str, Any]]:
        account_kind = await self._ensure_account_kind()
        if account_kind == "users":
            authenticated_login = await self._ensure_authenticated_login()
            if authenticated_login and authenticated_login.lower() == self._org.lower():
                # /users/{login}/repos only ever returns PUBLIC repos,
                # even for the token's own account — /user/repos (no
                # username, resolved from the token) is what includes
                # private ones too.
                return await self._paginated(
                    "/user/repos", affiliation="owner", visibility=self._repo_visibility
                )
        return await self._paginated(f"/{account_kind}/{self._org}/repos")

    def _apply_repo_filter(self, repos: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if self._selected_containers is None:
            return repos
        return [r for r in repos if r["full_name"] in self._selected_containers]

    async def discover_containers(self) -> list[SourceContainer]:
        account_kind = await self._ensure_account_kind()
        org_data = await self._request("GET", f"/{account_kind}/{self._org}")
        all_repos = await self._repos_request()
        self._repos_raw = self._apply_repo_filter(all_repos)
        org_raw = {
            "login": org_data["login"],
            "name": org_data.get("name") or org_data["login"],
            "html_url": org_data.get("html_url", ""),
        }
        return [mapper.map_organization(org_raw)]

    async def _ensure_repos(self) -> list[dict[str, Any]]:
        if self._repos_raw is None:
            all_repos = await self._repos_request()
            self._repos_raw = self._apply_repo_filter(all_repos)
        return self._repos_raw

    async def _ensure_branch_data(self, repo_full_name: str, branch: str) -> None:
        key = f"{repo_full_name}@{branch}"
        if key in self._tree_by_repo_branch:
            return
        branch_data = await self._request("GET", f"/repos/{repo_full_name}/branches/{branch}")
        sha = branch_data["commit"]["sha"]
        tree_data = await self._request(
            "GET", f"/repos/{repo_full_name}/git/trees/{sha}", params={"recursive": "1"}
        )
        self._tree_by_repo_branch[key] = [
            {"path": entry["path"], "type": "tree" if entry["type"] == "tree" else "blob"}
            for entry in tree_data.get("tree", [])
        ]
        commits = await self._paginated(f"/repos/{repo_full_name}/commits", sha=branch)
        self._commits_by_repo[repo_full_name] = commits
        for c in commits:
            self._commit_by_sha[f"{repo_full_name}@{c['sha']}"] = {
                "repo": repo_full_name,
                "sha": c["sha"],
                "message": c["commit"]["message"],
                "author": (c.get("commit", {}).get("author") or {}).get("email"),
                "html_url": c.get("html_url", ""),
            }

    async def _ensure_issues(self, repo_full_name: str) -> list[dict[str, Any]]:
        if repo_full_name not in self._issues_by_repo:
            raw_items = await self._paginated(f"/repos/{repo_full_name}/issues", state="all")
            # GitHub's /issues endpoint also returns pull requests
            # (flagged by a "pull_request" key) — those are fetched
            # separately via /pulls, with their own fuller PR fields.
            issues = [item for item in raw_items if "pull_request" not in item]
            self._issues_by_repo[repo_full_name] = issues
            for item in issues:
                native_id = f"{repo_full_name}#{item['number']}"
                self._issue_by_native_id[native_id] = {**item, "repo": repo_full_name}
        return self._issues_by_repo[repo_full_name]

    @staticmethod
    def _flatten_pr(pr: dict[str, Any], repo_full_name: str) -> dict[str, Any]:
        return {
            "repo": repo_full_name,
            "number": pr["number"],
            "title": pr["title"],
            "body": pr.get("body") or "",
            "state": pr.get("state"),
            "head_ref": (pr.get("head") or {}).get("ref"),
            "base_ref": (pr.get("base") or {}).get("ref"),
            "html_url": pr.get("html_url", ""),
            # Timestamps and author come back in the same /pulls response
            # and were being dropped here — which is why PR timestamp
            # coverage measured 0/138 and no cycle-time, stale-PR or
            # throughput question was answerable.
            "created_at": pr.get("created_at"),
            "updated_at": pr.get("updated_at"),
            "closed_at": pr.get("closed_at"),
            "merged_at": pr.get("merged_at"),
            "author": (pr.get("user") or {}).get("login"),
            "is_draft": pr.get("draft"),
            "labels": [lbl.get("name") for lbl in pr.get("labels") or [] if lbl.get("name")],
        }

    async def _ensure_pull_requests(self, repo_full_name: str) -> list[dict[str, Any]]:
        if repo_full_name not in self._pull_requests_by_repo:
            raw_prs = await self._paginated(f"/repos/{repo_full_name}/pulls", state="all")
            self._pull_requests_by_repo[repo_full_name] = raw_prs
            for pr in raw_prs:
                native_id = f"{repo_full_name}#{pr['number']}"
                self._pull_request_by_native_id[native_id] = self._flatten_pr(pr, repo_full_name)
        return self._pull_requests_by_repo[repo_full_name]

    async def _ensure_projects_v2(self) -> list[dict[str, Any]]:
        if self._projects_v2_raw is None:
            account_kind = await self._ensure_account_kind()
            owner_field = "organization" if account_kind == "orgs" else "user"
            query = _PROJECTS_V2_QUERY_TEMPLATE.replace("__OWNER_FIELD__", owner_field)
            projects: list[dict[str, Any]] = []
            after: str | None = None
            while True:
                data = await self._graphql(query, {"org": self._org, "after": after})
                owner_node = data.get(owner_field) or {}
                connection = owner_node.get("projectsV2") or {
                    "nodes": [],
                    "pageInfo": {"hasNextPage": False},
                }
                # A node can come back null rather than absent — a
                # FORBIDDEN error on that specific node (e.g. the PAT
                # lacks the "Projects" permission) nulls it out instead
                # of removing it from the list, per GraphQL's partial-
                # success semantics (_graphql already logged the error).
                projects.extend(n for n in connection.get("nodes", []) if n is not None)
                page_info = connection.get("pageInfo", {})
                if not page_info.get("hasNextPage"):
                    break
                after = page_info.get("endCursor")
            self._projects_v2_raw = projects
            for p in projects:
                native_id = f"projectV2:{p['id']}"
                self._project_v2_by_native_id[native_id] = p
                # "items" can itself be null (a narrower permission gap
                # than the whole node) even when the node survived —
                # (... or {}) guards that the same way the None-node
                # filter above guards the outer list.
                for item in (p.get("items") or {}).get("nodes", []) or []:
                    if item is None:
                        continue
                    item_native_id = f"projectV2item:{item['id']}"
                    self._project_v2_items_by_native_id[item_native_id] = {
                        **item,
                        "project_id": p["id"],
                    }
        return self._projects_v2_raw

    async def _ensure_ai_assets(self, repo_full_name: str) -> list[dict[str, Any]]:
        """AI Explorer entries — agents/skills/rules a repo declares for
        a coding assistant, tagged by vendor convention. Deliberately its
        own lightweight tree fetch rather than reusing
        `_ensure_branch_data` (the "code" entity type's tree fetch): that
        one also pages the repo's full commit history, which this
        doesn't need and shouldn't pay for just to find a handful of
        small files under .github/.claude/.cursor."""
        if repo_full_name in self._ai_assets_by_repo:
            return self._ai_assets_by_repo[repo_full_name]

        repos = await self._ensure_repos()
        repo_data = next(r for r in repos if r["full_name"] == repo_full_name)
        branch = repo_data.get("default_branch", "main")
        try:
            branch_data = await self._request("GET", f"/repos/{repo_full_name}/branches/{branch}")
            sha = branch_data["commit"]["sha"]
            tree_data = await self._request(
                "GET",
                f"/repos/{repo_full_name}/git/trees/{sha}",
                params={"recursive": "1"},
            )
        except (AuthError, NotFound) as exc:
            logger.warning("github.ai_assets_unavailable", repo=repo_full_name, error=str(exc))
            self._mark_degraded("ai_assets", str(exc))
            self._ai_assets_by_repo[repo_full_name] = []
            return []

        assets: list[dict[str, Any]] = []
        for entry in tree_data.get("tree", []):
            if entry.get("type") != "blob":
                continue
            path = entry["path"]
            classified = mapper.classify_ai_asset_path(path)
            if classified is None:
                continue
            vendor, asset_type = classified
            content = await self._request(
                "GET", f"/repos/{repo_full_name}/contents/{path}", params={"ref": branch}
            )
            text = base64.b64decode(content.get("content", "")).decode("utf-8", errors="replace")
            fallback_name = posixpath.basename(path).rsplit(".", 1)[0]
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
        self._ai_assets_by_repo[repo_full_name] = assets
        return assets

    async def list_children(self, parent_id: str, cursor: str | None = None) -> Page[SourceObject]:
        repos = await self._ensure_repos()
        repo_full_names = {r["full_name"] for r in repos}

        if parent_id == self._org:
            items = [
                mapper.map_repository(
                    {
                        "full_name": r["full_name"],
                        "name": r["name"],
                        "owner": self._org,
                        "default_branch": r.get("default_branch", "main"),
                        "description": r.get("description") or "",
                        "html_url": r.get("html_url", ""),
                    }
                )
                for r in repos
            ]
            if "projects" in self._entity_types:
                projects = await self._ensure_projects_v2()
                items += [
                    mapper.map_project_v2(
                        {
                            "id": p["id"],
                            "title": p["title"],
                            "org": self._org,
                            "number": p.get("number"),
                            "url": p.get("url", ""),
                        }
                    )
                    for p in projects
                ]
            return Page(items=items, next_cursor=None)

        if parent_id in repo_full_names:
            items = []
            if "code" in self._entity_types:
                repo_data = next(r for r in repos if r["full_name"] == parent_id)
                branch = repo_data.get("default_branch", "main")
                items.append(
                    mapper.map_branch({"repo": parent_id, "name": branch, "commit_sha": ""})
                )
            if "issues" in self._entity_types:
                issues = await self._ensure_issues(parent_id)
                items += [mapper.map_issue({**i, "repo": parent_id}) for i in issues]
            if "pull_requests" in self._entity_types:
                prs = await self._ensure_pull_requests(parent_id)
                items += [mapper.map_pull_request(self._flatten_pr(pr, parent_id)) for pr in prs]
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

        if parent_id.startswith("projectV2:") and parent_id in self._project_v2_by_native_id:
            project = self._project_v2_by_native_id[parent_id]
            items = []
            for item in (project.get("items") or {}).get("nodes", []) or []:
                if item is None:
                    continue
                content = item.get("content") or {}
                items.append(
                    mapper.map_project_v2_item(
                        {
                            "id": item["id"],
                            "project_id": project["id"],
                            "title": content.get("title"),
                            "content_type": content.get("__typename"),
                            "content_url": content.get("url", ""),
                        }
                    )
                )
            return Page(items=items, next_cursor=None)

        repo, branch, path = mapper.parse_ref(parent_id)
        if repo not in repo_full_names:
            return Page(items=[], next_cursor=None)
        await self._ensure_branch_data(repo, branch)

        tree = self._tree_by_repo_branch.get(f"{repo}@{branch}", [])
        items = [
            mapper.map_tree_entry(repo, branch, entry)
            for entry in tree
            if posixpath.dirname(entry["path"]) == (path or "")
        ]
        if path is None:
            commits = self._commits_by_repo.get(repo, [])
            items += [
                mapper.map_commit(
                    {
                        "repo": repo,
                        "sha": c["sha"],
                        "message": c["commit"]["message"],
                        "author": (c.get("commit", {}).get("author") or {}).get("email"),
                        "html_url": c.get("html_url", ""),
                    }
                )
                for c in commits
            ]
        return Page(items=items, next_cursor=None)

    # -- single-object lookups -------------------------------------------

    async def get_object(self, native_id: str) -> SourceObject:
        repos = await self._ensure_repos()
        for r in repos:
            if r["full_name"] == native_id:
                return mapper.map_repository(
                    {
                        "full_name": r["full_name"],
                        "name": r["name"],
                        "owner": self._org,
                        "default_branch": r.get("default_branch", "main"),
                        "description": r.get("description") or "",
                        "html_url": r.get("html_url", ""),
                    }
                )
        if native_id in self._commit_by_sha:
            return mapper.map_commit(self._commit_by_sha[native_id])
        if native_id in self._issue_by_native_id:
            return mapper.map_issue(self._issue_by_native_id[native_id])
        if native_id in self._pull_request_by_native_id:
            return mapper.map_pull_request(self._pull_request_by_native_id[native_id])
        if native_id in self._project_v2_by_native_id:
            p = self._project_v2_by_native_id[native_id]
            return mapper.map_project_v2(
                {
                    "id": p["id"],
                    "title": p["title"],
                    "org": self._org,
                    "number": p.get("number"),
                    "url": p.get("url", ""),
                }
            )
        if native_id in self._project_v2_items_by_native_id:
            item = self._project_v2_items_by_native_id[native_id]
            content = item.get("content") or {}
            return mapper.map_project_v2_item(
                {
                    "id": item["id"],
                    "project_id": item["project_id"],
                    "title": content.get("title"),
                    "content_type": content.get("__typename"),
                    "content_url": content.get("url", ""),
                }
            )
        raise NotFound(
            f"no GitHub object with native_id={native_id!r}", source_system=self.source_system
        )

    async def get_content(self, native_id: str, version: str | None = None) -> SourceContent:
        # PR/Issue bodies — fetched already, resident in memory from
        # sync, never persisted to the node's own attributes (ADR-003;
        # a real PR description can run tens of KB). Returned here
        # on-demand instead — same on-demand pattern as the repo-file
        # case below, just no extra API call needed since the body is
        # already sitting in the raw dict this sync pass already has.
        if native_id in self._pull_request_by_native_id:
            pr = self._pull_request_by_native_id[native_id]
            return mapper.map_content(
                {
                    "native_id": native_id,
                    "mime_type": "text/markdown",
                    "text": pr.get("body") or "",
                    "url": pr.get("html_url", ""),
                }
            )
        if native_id in self._issue_by_native_id:
            issue = self._issue_by_native_id[native_id]
            return mapper.map_content(
                {
                    "native_id": native_id,
                    "mime_type": "text/markdown",
                    "text": issue.get("body") or "",
                    "url": issue.get("html_url", ""),
                }
            )

        # AI assets (agent/skill/rule definitions) — the body is what makes
        # one runnable: a caller discovers "this repo has a security-auditor
        # agent" through the catalog, then fetches the definition here and
        # hands it to whatever runtime actually executes agents. Fetched
        # from the default branch, since that's where _ensure_ai_assets
        # listed them.
        ai_asset = mapper.parse_ai_asset_ref(native_id)
        if ai_asset is not None:
            repo_full_name, asset_path = ai_asset
            repo_data = await self._request("GET", f"/repos/{repo_full_name}")
            data = await self._request(
                "GET",
                f"/repos/{repo_full_name}/contents/{asset_path}",
                params={"ref": repo_data.get("default_branch", "main")},
            )
            return mapper.map_content(
                {
                    "native_id": native_id,
                    "mime_type": "text/markdown",
                    "text": base64.b64decode(data.get("content", "")).decode(
                        "utf-8", errors="replace"
                    ),
                    "url": data.get("html_url", ""),
                }
            )

        repo, branch, path = mapper.parse_ref(native_id)
        if path is None:
            raise NotFound(
                f"no content for native_id={native_id!r}", source_system=self.source_system
            )
        data = await self._request("GET", f"/repos/{repo}/contents/{path}", params={"ref": branch})
        text = base64.b64decode(data.get("content", "")).decode("utf-8", errors="replace")
        content_raw = {
            "native_id": native_id,
            "mime_type": "text/plain",
            "text": text,
            "url": data.get("html_url", ""),
        }
        return mapper.map_content(content_raw)

    # -- change feed / links / acl ----------------------------------------

    async def get_changes(self, cursor: str | None = None) -> ChangePage:
        # No cheap "deleted files" feed via the REST API without diffing
        # commits ourselves — not implemented for this fast-tracked pass.
        return ChangePage(items=[], next_cursor=None, has_more=False)

    async def get_links(self, native_id: str) -> list[SourceLink]:
        # Previously only commits were ever scanned — Issues and PRs
        # (the objects most likely to actually reference a work item or
        # another PR) never had their bodies checked for cross-references
        # at all. Title is scanned alongside body — a real gap found via
        # live testing: "AB#56 Assign skills to an employee profile" put
        # the whole reference in the title with an empty body, which the
        # body-only scan silently missed.
        # Title and body are scanned *separately*, not concatenated. Where a
        # reference sits is the strongest signal about what it means: a work
        # item id in a pull request title is the author declaring "this PR
        # does that work" (an IMPLEMENTS edge, confident enough to skip
        # review), while the same id in the body is a mention. Concatenating
        # them threw that signal away and scored both as weakly as possible —
        # which matters most here, since GitHub PRs are where this project's
        # real cross-system references to Azure Boards actually live.
        if native_id in self._commit_by_sha:
            repo_full_name = native_id.split("@", 1)[0]
            message = self._commit_by_sha[native_id]["message"]
            return mapper.map_links_from_text(
                native_id, message, repo_full_name=repo_full_name, location="commit_message"
            )
        if native_id in self._issue_by_native_id:
            issue = self._issue_by_native_id[native_id]
            return mapper.map_links_from_text(
                native_id, issue.get("title") or "", repo_full_name=issue["repo"],
                location="title",
            ) + mapper.map_links_from_text(
                native_id, issue.get("body") or "", repo_full_name=issue["repo"],
                location="body",
            )
        if native_id in self._pull_request_by_native_id:
            pr = self._pull_request_by_native_id[native_id]
            # Branch name was never scanned before this — a real gap found
            # against this project's own data: 14 of 25 real PR branches
            # carry a ticket key (e.g. "feature/AB-44", "design/WI-616"),
            # a convention at least as common here as putting the key in
            # the title.
            return (
                mapper.map_links_from_text(
                    native_id, pr.get("title") or "", repo_full_name=pr["repo"], location="title"
                )
                + mapper.map_links_from_text(
                    native_id, pr.get("head_ref") or "", repo_full_name=pr["repo"],
                    location="branch",
                )
                + mapper.map_links_from_text(
                    native_id, pr.get("body") or "", repo_full_name=pr["repo"], location="body"
                )
            )
        return []

    async def get_acl_reference(self, native_id: str) -> ACLReference:
        return ACLReference(native_id=native_id, acl_ref={"org": self._org})
