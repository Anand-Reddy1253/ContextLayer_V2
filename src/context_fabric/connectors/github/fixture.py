"""GitHub fixture-mode connector.

Reads fixtures/github/*.json — no network, no credentials. Native
hierarchy: Organization -> Repository -> Branch -> Directory -> File
(docs/CONNECTORS.md). Pull requests, commits, and Actions runs are
separate SourceObject kinds parented by repository, retrievable via
get_object but not returned by list_children — the same pattern
connectors/azure_devops/fixture.py established for PRs/builds.
"""

from __future__ import annotations

import posixpath
from pathlib import Path
from typing import Any

from context_fabric.connectors.base import FixtureConnectorBase
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
from context_fabric.domain.errors import NotFound

_PAGE_SIZE = 2
_CHANGES_PAGE_SIZE = 1

_TREE_FILES = {
    "acme-org/identity-service": "tree/identity-service.json",
    "acme-org/sso-gateway": "tree/sso-gateway.json",
}


class GitHubFixtureConnector(FixtureConnectorBase):
    source_system = "github"

    def __init__(self, fixtures_dir: Path | None = None) -> None:
        super().__init__(fixtures_dir)
        self._orgs_raw: list[dict[str, Any]] = self.load_json("organizations.json")
        self._repos_raw: list[dict[str, Any]] = self.load_json("repositories.json")
        self._branches_raw: list[dict[str, Any]] = self.load_json("branches.json")
        self._pull_requests_raw: list[dict[str, Any]] = self.load_json("pull_requests.json")
        self._commits_raw: list[dict[str, Any]] = self.load_json("commits.json")
        self._actions_runs_raw: list[dict[str, Any]] = self.load_json("actions_runs.json")
        self._file_contents_raw: list[dict[str, Any]] = self.load_json("file_contents.json")
        self._changes_raw: dict[str, Any] = self.load_json("changes.json")
        self._acl_raw: list[dict[str, Any]] = self.load_json("acl.json")

        self._org_logins = {o["login"] for o in self._orgs_raw}
        self._repo_full_names = {r["full_name"] for r in self._repos_raw}
        self._tree_raw_by_repo: dict[str, list[dict[str, Any]]] = {
            repo: self.load_json(path) for repo, path in _TREE_FILES.items()
        }

    # -- discovery / hierarchy ------------------------------------------

    async def discover_containers(self) -> list[SourceContainer]:
        return [mapper.map_organization(o) for o in self._orgs_raw]

    async def list_children(
        self, parent_id: str, cursor: str | None = None
    ) -> Page[SourceObject]:
        return self._paginate(self._children_of(parent_id), cursor)

    def _children_of(self, parent_id: str) -> list[SourceObject]:
        if parent_id in self._org_logins:
            return [mapper.map_repository(r) for r in self._repos_raw if r["owner"] == parent_id]
        if parent_id in self._repo_full_names:
            return [mapper.map_branch(b) for b in self._branches_raw if b["repo"] == parent_id]

        repo, branch_or_sha, path = mapper.parse_ref(parent_id)

        # A commit's native_id ("repo@sha") is structurally identical in
        # shape to a branch's ("repo@branch_name") — parent_id alone can't
        # tell them apart. Commits are leaves (no children); returning []
        # for one here is what stops list_children(commit_id) from
        # re-deriving the branch's own root entries + commit list forever,
        # which is exactly the infinite BFS growth this guard exists to
        # prevent — caught empirically (a pytest run that never returned)
        # before this was corrected.
        is_known_branch = any(
            b["repo"] == repo and b["name"] == branch_or_sha for b in self._branches_raw
        )
        if path is None and not is_known_branch:
            return []

        tree = self._tree_raw_by_repo.get(repo, [])
        entries = [
            mapper.map_tree_entry(repo, branch_or_sha, entry)
            for entry in tree
            if posixpath.dirname(entry["path"]) == (path or "")
        ]
        if path is None:
            # A branch's children are its root tree entries *and* its
            # commits (docs/CONNECTORS.md "Also surfaces: ... Commits") —
            # unlike PRs/Actions runs, commits need to be walked so their
            # own get_links() mentions get extracted (Phase 7); a commit
            # reachable only via get_object() would never be synced at
            # all, since nothing but list_children ever discovers a
            # native_id to sync.
            commits = [mapper.map_commit(c) for c in self._commits_raw if c["repo"] == repo]
            entries = [*entries, *commits]
        return entries

    @staticmethod
    def _paginate(items: list[SourceObject], cursor: str | None) -> Page[SourceObject]:
        start = int(cursor) if cursor else 0
        end = start + _PAGE_SIZE
        page_items = items[start:end]
        next_cursor = str(end) if end < len(items) else None
        return Page(items=page_items, next_cursor=next_cursor)

    # -- single-object lookups -------------------------------------------

    async def get_object(self, native_id: str) -> SourceObject:
        if native_id in self._repo_full_names:
            raw = next(r for r in self._repos_raw if r["full_name"] == native_id)
            return mapper.map_repository(raw)

        for pr_raw in self._pull_requests_raw:
            if f"{pr_raw['repo']}#{pr_raw['number']}" == native_id:
                return mapper.map_pull_request(pr_raw)

        for commit_raw in self._commits_raw:
            if f"{commit_raw['repo']}@{commit_raw['sha']}" == native_id:
                return mapper.map_commit(commit_raw)

        for run_raw in self._actions_runs_raw:
            if f"{run_raw['repo']}/actions/{run_raw['run_id']}" == native_id:
                return mapper.map_actions_run(run_raw)

        if "@" in native_id:
            repo, branch, path = mapper.parse_ref(native_id)
            if path is None:
                branch_raw = next(
                    (b for b in self._branches_raw if b["repo"] == repo and b["name"] == branch),
                    None,
                )
                if branch_raw:
                    return mapper.map_branch(branch_raw)
            else:
                entry = next(
                    (e for e in self._tree_raw_by_repo.get(repo, []) if e["path"] == path), None
                )
                if entry:
                    return mapper.map_tree_entry(repo, branch, entry)

        raise NotFound(
            f"no GitHub object with native_id={native_id!r}", source_system=self.source_system
        )

    async def get_content(self, native_id: str, version: str | None = None) -> SourceContent:
        raw = next((c for c in self._file_contents_raw if c["native_id"] == native_id), None)
        if raw is None:
            raise NotFound(
                f"no content for native_id={native_id!r}", source_system=self.source_system
            )
        return mapper.map_content(raw)

    # -- change feed / links / acl ----------------------------------------

    async def get_changes(self, cursor: str | None = None) -> ChangePage:
        all_changes = self._changes_raw["items"]
        start = int(cursor) if cursor else 0
        end = start + _CHANGES_PAGE_SIZE
        page_raw = all_changes[start:end]
        next_cursor = str(end) if end < len(all_changes) else None

        items: list[SourceObject] = []
        for change in page_raw:
            native_id = change["native_id"]
            kind = change["kind"]
            if change["changeType"] == "deleted":
                items.append(mapper.map_tombstone(native_id, kind))
                continue
            repo, branch, path = mapper.parse_ref(native_id)
            entry = next(
                (e for e in self._tree_raw_by_repo.get(repo, []) if e["path"] == path), None
            )
            items.append(
                mapper.map_tree_entry(repo, branch, entry)
                if entry
                else mapper.map_tombstone(native_id, kind)
            )

        return ChangePage(items=items, next_cursor=next_cursor, has_more=next_cursor is not None)

    async def get_links(self, native_id: str) -> list[SourceLink]:
        for pr_raw in self._pull_requests_raw:
            if f"{pr_raw['repo']}#{pr_raw['number']}" == native_id:
                # Title is scanned alongside body — a reference can live
                # entirely in the title (e.g. "AB#56 Assign skills..."),
                # which a body-only scan would silently miss.
                text = f"{pr_raw.get('title') or ''}\n{pr_raw.get('body') or ''}"
                return mapper.map_links_from_text(native_id, text, repo_full_name=pr_raw["repo"])
        for commit_raw in self._commits_raw:
            if f"{commit_raw['repo']}@{commit_raw['sha']}" == native_id:
                return mapper.map_links_from_text(
                    native_id, commit_raw.get("message", ""), repo_full_name=commit_raw["repo"]
                )
        return []

    async def get_acl_reference(self, native_id: str) -> ACLReference:
        for raw in self._acl_raw:
            if raw["native_id"] == native_id:
                return mapper.map_acl(raw)
        raise NotFound(
            f"no ACL reference for native_id={native_id!r}", source_system=self.source_system
        )
