"""GitHub payload -> domain/ type mapping.

The only module in connectors/github/ allowed to know GitHub's REST/
GraphQL JSON shape (docs/CONNECTORS.md "Adding a new connector"). Native
hierarchy is tree-based (Organization -> Repository -> Branch ->
Directory -> File), genuinely different from ADO's area-path-based one —
hierarchy here is derived from tree-entry `path` strings via
`posixpath.dirname`, not an explicit parent field.
"""

from __future__ import annotations

import hashlib
import json
import posixpath
import re
from typing import Any

import yaml

from context_fabric.domain.connector_types import (
    ACLReference,
    SourceContainer,
    SourceContent,
    SourceLink,
    SourceObject,
)

# AI Explorer (docs/UI.md "AI Explorer" — pulls agents/skills/rules a repo
# declares for a coding assistant to use, tagged by which vendor's
# convention they follow). Each entry is (path-prefix, vendor, asset_type);
# checked longest-prefix-first isn't needed since prefixes don't overlap.
def _snippet(text: str, match_start: int, match_end: int, *, radius: int = 80) -> str:
    """The window of text around a regex match, shown to a Proposed
    Links reviewer as evidence for why an edge was proposed."""
    start = max(0, match_start - radius)
    end = min(len(text), match_end + radius)
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(text) else ""
    return f"{prefix}{text[start:end].strip()}{suffix}"


AI_ASSET_PATH_RULES: list[tuple[str, str, str]] = [
    (".github/agents/", "github", "agent"),
    (".github/skills/", "github", "skill"),
    (".github/prompts/", "github", "prompt"),
    (".claude/agents/", "claude", "agent"),
    (".claude/skills/", "claude", "skill"),
    (".claude/commands/", "claude", "command"),
    (".cursor/rules/", "cursor", "rule"),
]

_FRONTMATTER_PATTERN = re.compile(r"^---\s*\n(.*?\n)---\s*\n", re.DOTALL)


def classify_ai_asset_path(path: str) -> tuple[str, str] | None:
    """Returns (vendor, asset_type) if `path` falls under a recognized
    AI-asset directory, else None — used to decide, from the repo's tree
    listing alone (no content fetch needed yet), which files are even
    worth fetching. Agent/skill/rule definitions are always markdown
    (`.md`) — a `.json` or other file sitting in the same directory
    (e.g. a `scope-map.json` config alongside real agent files) is
    support tooling, not a definition, and is excluded."""
    if not path.endswith(".md"):
        return None
    for prefix, vendor, asset_type in AI_ASSET_PATH_RULES:
        if path.startswith(prefix) and path != prefix:
            return vendor, asset_type
    return None


def parse_ai_asset_description(text: str, *, fallback_name: str) -> tuple[str, str]:
    """(name, description) from a skill/agent/rule file's own YAML
    frontmatter (`name:`/`description:`, the convention all three
    vendors use) when present; otherwise the first non-empty line of
    body text, truncated — a short excerpt only, never the full body
    (ADR-003: this is metadata for a catalog card, not a content
    replica)."""
    match = _FRONTMATTER_PATTERN.match(text)
    if match:
        try:
            data = yaml.safe_load(match.group(1)) or {}
        except yaml.YAMLError:
            data = {}
        if isinstance(data, dict):
            name = str(data.get("name") or fallback_name)
            description = str(data.get("description") or "")
            if description:
                return name, description[:300]
    for line in text.splitlines():
        stripped = line.strip().lstrip("#").strip()
        if stripped:
            return fallback_name, stripped[:300]
    return fallback_name, ""

_MENTION_PATTERN = re.compile(r"AB#(\d+)")
# GitHub's own cross-reference syntax — "owner/repo#42" (cross-repo,
# already fully qualified) and bare "#42" (same-repo, needs the calling
# repo's full_name to become GitHub's own native_id shape "{repo}#{N}").
# The negative lookbehind on the same-repo pattern stops it from also
# matching the "#42" tail of an "owner/repo#42" cross-repo reference —
# that character is preceded by a repo-name character, never a boundary.
_GITHUB_CROSS_REPO_REF_PATTERN = re.compile(r"\b([\w.-]+/[\w.-]+)#(\d+)\b")
_GITHUB_SAME_REPO_REF_PATTERN = re.compile(r"(?<![\w./-])#(\d+)\b")
# Jira's own issue-key shape ("PROJ-123") — see
# synchronization/link_extraction.py's LINK_PATTERNS for why this is
# resolvable on its own without a repo/instance qualifier.
_JIRA_KEY_PATTERN = re.compile(r"\b([A-Z][A-Z0-9]{1,9}-\d+)\b")


def _content_hash(raw: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(raw, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def branch_native_id(repo_full_name: str, branch_name: str) -> str:
    return f"{repo_full_name}@{branch_name}"


def tree_entry_native_id(repo_full_name: str, branch_name: str, path: str) -> str:
    return f"{branch_native_id(repo_full_name, branch_name)}:{path}"


def parse_ref(native_id: str) -> tuple[str, str, str | None]:
    """repo@branch:path -> (repo, branch, path|None). Inverse of
    branch_native_id/tree_entry_native_id — shared by fixture.py and
    live.py, both of which need to decode a native_id back into its
    parts."""
    repo, _, rest = native_id.partition("@")
    branch, _, path = rest.partition(":")
    return repo, branch, path or None


def map_organization(raw: dict[str, Any]) -> SourceContainer:
    return SourceContainer(
        id=raw["login"],
        name=raw.get("name", raw["login"]),
        kind="ORGANIZATION",
        parent_id=None,
        native_id=raw["login"],
        attributes={"url": raw.get("html_url", "")},
    )


def map_repository(raw: dict[str, Any]) -> SourceObject:
    return SourceObject(
        native_id=raw["full_name"],
        kind="REPOSITORY",
        name=raw["name"],
        parent_native_id=raw["owner"],
        attributes={
            "default_branch": raw.get("default_branch", "main"),
            "url": raw.get("html_url", ""),
        },
        description=(raw.get("description") or "")[:512] or None,
        content_hash=_content_hash(raw),
    )


def map_ai_asset(
    repo_full_name: str, path: str, *, vendor: str, asset_type: str, name: str, description: str
) -> SourceObject:
    return SourceObject(
        native_id=f"{repo_full_name}:ai-asset:{path}",
        kind="AI_ASSET",
        name=name,
        parent_native_id=repo_full_name,
        attributes={
            "vendor": vendor,
            "asset_type": asset_type,
            "path": path,
        },
        description=description or None,
        content_hash=hashlib.sha256(description.encode("utf-8")).hexdigest(),
    )


def map_branch(raw: dict[str, Any]) -> SourceObject:
    return SourceObject(
        native_id=branch_native_id(raw["repo"], raw["name"]),
        kind="BRANCH",
        name=raw["name"],
        parent_native_id=raw["repo"],
        attributes={"commit_sha": raw.get("commit_sha", "")},
        content_hash=_content_hash(raw),
    )


def map_tree_entry(repo_full_name: str, branch_name: str, raw: dict[str, Any]) -> SourceObject:
    path = raw["path"]
    parent_path = posixpath.dirname(path)
    parent_native_id = (
        tree_entry_native_id(repo_full_name, branch_name, parent_path)
        if parent_path
        else branch_native_id(repo_full_name, branch_name)
    )
    kind = "DIRECTORY" if raw["type"] == "tree" else "FILE"
    return SourceObject(
        native_id=tree_entry_native_id(repo_full_name, branch_name, path),
        kind=kind,
        name=posixpath.basename(path),
        parent_native_id=parent_native_id,
        attributes={"path": path},
        content_hash=_content_hash(raw),
    )


def map_tombstone(native_id: str, kind: str) -> SourceObject:
    return SourceObject(native_id=native_id, kind=kind, name="", deleted=True)


def map_pull_request(raw: dict[str, Any]) -> SourceObject:
    return SourceObject(
        native_id=f"{raw['repo']}#{raw['number']}",
        kind="PULL_REQUEST",
        name=raw["title"],
        parent_native_id=raw["repo"],
        attributes={
            "state": raw.get("state"),
            "head_ref": raw.get("head_ref"),
            "base_ref": raw.get("base_ref"),
            "url": raw.get("html_url", ""),
            # Deliberately not "body" — a real PR description can run to
            # tens of KB (one in this project's own real data is 17.7KB)
            # and ADR-003 fetches full content on-demand via
            # get_content() rather than eagerly duplicating it into every
            # synced node's attributes, same as ADO's map_work_item and
            # Confluence's map_page already do. This was a real gap this
            # connector had — get_content() only handled repo file paths,
            # not PR/Issue bodies at all — fixed alongside this change.
        },
        content_hash=_content_hash(raw),
    )


def map_issue(raw: dict[str, Any]) -> SourceObject:
    """A GitHub Issue. GitHub's REST /issues endpoint also returns pull
    requests (distinguishable only by the presence of a "pull_request"
    key) — callers must filter those out before mapping, since PRs are
    fetched (with their fuller PR-specific fields) via map_pull_request
    instead."""
    return SourceObject(
        native_id=f"{raw['repo']}#{raw['number']}",
        kind="ISSUE",
        name=raw["title"],
        parent_native_id=raw["repo"],
        attributes={
            "state": raw.get("state"),
            "labels": raw.get("labels", []),
            "url": raw.get("html_url", ""),
            # Deliberately not "body" — see map_pull_request's comment.
        },
        content_hash=_content_hash(raw),
    )


def map_project_v2(raw: dict[str, Any]) -> SourceObject:
    """A GitHub Projects (v2) board — org-scoped, fetched via GraphQL
    (there is no REST equivalent). Parented by the organization, sibling
    to repositories."""
    return SourceObject(
        native_id=f"projectV2:{raw['id']}",
        kind="PROJECT_BOARD",
        name=raw["title"],
        parent_native_id=raw["org"],
        attributes={"number": raw.get("number"), "url": raw.get("url", "")},
        content_hash=_content_hash(raw),
    )


def map_project_v2_item(raw: dict[str, Any]) -> SourceObject:
    """One card/item on a Projects (v2) board — a lightweight pointer at
    whatever it wraps (an Issue, a PR, or a draft with no backing
    object), not a full copy of that object's own fields."""
    return SourceObject(
        native_id=f"projectV2item:{raw['id']}",
        kind="PROJECT_ITEM",
        name=raw.get("title") or "(untitled)",
        parent_native_id=f"projectV2:{raw['project_id']}",
        attributes={
            "content_type": raw.get("content_type"),
            "content_url": raw.get("content_url", ""),
        },
        content_hash=_content_hash(raw),
    )


def map_commit(raw: dict[str, Any]) -> SourceObject:
    return SourceObject(
        native_id=f"{raw['repo']}@{raw['sha']}",
        kind="COMMIT",
        name=raw["message"].splitlines()[0],
        parent_native_id=raw["repo"],
        attributes={
            "message": raw.get("message", ""),
            "author": raw.get("author"),
            "url": raw.get("html_url", ""),
        },
        content_hash=_content_hash(raw),
    )


def map_actions_run(raw: dict[str, Any]) -> SourceObject:
    return SourceObject(
        native_id=f"{raw['repo']}/actions/{raw['run_id']}",
        kind="BUILD",
        name=f"{raw['name']} #{raw['run_id']}",
        parent_native_id=raw["repo"],
        attributes={
            "status": raw.get("status"),
            "conclusion": raw.get("conclusion"),
            "head_sha": raw.get("head_sha"),
            "url": raw.get("html_url", ""),
        },
        content_hash=_content_hash(raw),
    )


def map_content(raw: dict[str, Any]) -> SourceContent:
    return SourceContent(
        native_id=raw["native_id"],
        mime_type=raw.get("mime_type", "text/plain"),
        text=raw.get("text", ""),
        uri=raw.get("url", ""),
    )


def map_links_from_text(
    native_id: str, text: str, *, repo_full_name: str | None = None
) -> list[SourceLink]:
    """Cross-reference extraction from a PR body / commit message / issue
    body — both ADO's "AB#NNN" convention and GitHub's own "#NN"
    (same-repo) / "owner/repo#NN" (cross-repo) issue-or-PR reference
    syntax, which this connector previously never looked for at all.
    `repo_full_name` resolves a same-repo "#NN" into GitHub's own native_id
    shape ("{repo}#{NN}", used for both Issues and PRs) — without it, only
    AB# and cross-repo refs (already fully qualified) are extracted."""
    links = [
        SourceLink(
            from_native_id=native_id,
            target_ref=f"AB#{m.group(1)}",
            link_kind="mentions",
            evidence=f'Found in the text: "{_snippet(text, m.start(), m.end())}"',
        )
        for m in _MENTION_PATTERN.finditer(text)
    ]
    links += [
        SourceLink(
            from_native_id=native_id,
            target_ref=f"{m.group(1)}#{m.group(2)}",
            link_kind="mentions",
            evidence=f'Found in the text: "{_snippet(text, m.start(), m.end())}"',
        )
        for m in _GITHUB_CROSS_REPO_REF_PATTERN.finditer(text)
    ]
    if repo_full_name:
        links += [
            SourceLink(
                from_native_id=native_id,
                target_ref=f"{repo_full_name}#{m.group(1)}",
                link_kind="mentions",
                evidence=f'Found in the text: "{_snippet(text, m.start(), m.end())}"',
            )
            for m in _GITHUB_SAME_REPO_REF_PATTERN.finditer(text)
        ]
    links += [
        SourceLink(
            from_native_id=native_id,
            target_ref=m.group(1),
            link_kind="mentions",
            evidence=f'Found in the text: "{_snippet(text, m.start(), m.end())}"',
        )
        for m in _JIRA_KEY_PATTERN.finditer(text)
    ]
    return links


def map_acl(raw: dict[str, Any]) -> ACLReference:
    return ACLReference(native_id=raw["native_id"], acl_ref=raw["acl_ref"])
