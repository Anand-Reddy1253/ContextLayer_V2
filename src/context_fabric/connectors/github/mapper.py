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

from context_fabric.connectors.cross_references import extract_cross_references
from context_fabric.domain.connector_types import (
    ACLReference,
    SourceContainer,
    SourceContent,
    SourceLink,
    SourceObject,
)

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


def _content_hash(raw: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(raw, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def branch_native_id(repo_full_name: str, branch_name: str) -> str:
    return f"{repo_full_name}@{branch_name}"


def tree_entry_native_id(repo_full_name: str, branch_name: str, path: str) -> str:
    return f"{branch_native_id(repo_full_name, branch_name)}:{path}"


_AI_ASSET_MARKER = ":ai-asset:"


def ai_asset_native_id(repo_full_name: str, path: str) -> str:
    return f"{repo_full_name}{_AI_ASSET_MARKER}{path}"


def parse_ai_asset_ref(native_id: str) -> tuple[str, str] | None:
    """(repo_full_name, path) for an AI_ASSET native_id, else None.

    AI assets deliberately don't carry a branch in their native_id (they
    come from the repo's default branch), so they don't fit parse_ref's
    "repo@branch:path" shape — which silently returned path=None for them,
    making get_content() raise NotFound for every agent and skill in the
    catalog. That meant the AI Explorer could tell you an agent existed
    but never hand back the definition needed to actually run it."""
    repo, marker, path = native_id.partition(_AI_ASSET_MARKER)
    if not marker or not path:
        return None
    return repo, path


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
        native_id=ai_asset_native_id(repo_full_name, path),
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
            # Present in the same /pulls payload (live.py's _flatten_pr
            # carries them through) — cycle time is closed_at/merged_at
            # minus created_at, and neither existed before.
            "created_at": raw.get("created_at"),
            "updated_at": raw.get("updated_at"),
            "closed_at": raw.get("closed_at"),
            "merged_at": raw.get("merged_at"),
            "author": raw.get("author"),
            "is_draft": raw.get("is_draft"),
            "labels": raw.get("labels", []),
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
            # GitHub's /issues payload reaches the mapper unflattened, so
            # labels arrive as objects — flatten to names so the
            # `containsAny` array operator can filter on them.
            "labels": [
                lbl.get("name") if isinstance(lbl, dict) else lbl
                for lbl in raw.get("labels") or []
            ],
            "url": raw.get("html_url", ""),
            "created_at": raw.get("created_at"),
            "updated_at": raw.get("updated_at"),
            "closed_at": raw.get("closed_at"),
            "author": (raw.get("user") or {}).get("login"),
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
    native_id: str,
    text: str,
    *,
    repo_full_name: str | None = None,
    location: str = "text",
) -> list[SourceLink]:
    """Cross-reference extraction from a PR title/body, commit message or
    issue body. Patterns live in connectors/cross_references.py so every
    connector recognizes the same reference shapes — this connector used
    to carry its own copies and, like the others, was missing some
    (Confluence page links were unrecognizable from here).

    `repo_full_name` resolves a same-repo "#NN" into GitHub's own native_id
    shape ("{repo}#{NN}", used for both Issues and PRs) — without it, only
    fully-qualified refs are extracted. `location` says which field the
    text came from, which drives the relationship type and confidence."""
    return extract_cross_references(
        native_id,
        text,
        location=location,
        repo_full_name=repo_full_name,
        skip_ref=lambda ref: ref == native_id,
    )


def map_acl(raw: dict[str, Any]) -> ACLReference:
    return ACLReference(native_id=raw["native_id"], acl_ref=raw["acl_ref"])
