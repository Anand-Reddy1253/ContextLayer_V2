"""Jira Cloud payload -> domain/ type mapping.

The only module in connectors/jira/ allowed to know Jira's REST API v3
JSON shape (docs/CONNECTORS.md "Adding a new connector"). Native
hierarchy: Project -> Issue -> child Issue (sub-tasks, or epic children in
team-managed projects), with Comments as leaves parented by the issue
they belong to.

Jira issue keys ("PROJ-123") are used directly as native_id — Jira's own
convention already gives every issue a globally-recognizable identifier,
so unlike ADO's opaque numeric ids there's no need for an "AB#"-style
prefix. This also means an issue key typed into any *other* connector's
free text (a GitHub PR description, an ADO work item, a Confluence page)
is already a directly resolvable cross-system reference, once
synchronization/link_extraction.py's LINK_PATTERNS knows the shape.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from context_fabric.domain.connector_types import (
    ACLReference,
    SourceContainer,
    SourceContent,
    SourceLink,
    SourceObject,
)

ISSUE_TYPE_TO_KIND = {
    "Epic": "EPIC",
    "Story": "STORY",
    "Task": "TASK",
    "Bug": "BUG",
    "Sub-task": "SUBTASK",
}

_MENTION_PATTERN = re.compile(r"AB#(\d+)")
_PR_MENTION_PATTERN = re.compile(r"\bPR-(\d+)\b")
_GITHUB_CROSS_REPO_REF_PATTERN = re.compile(r"\b([\w.-]+/[\w.-]+)#(\d+)\b")

# Jira's own issue-link relationship types (`fields.issuelinks[].type.name`)
# — real, human-curated cross-references from Jira's own linking feature,
# distinct from both the parent/child hierarchy (fields.parent, already
# read by map_issue) and free-text mentions. Most Jira instances only ever
# use a handful of built-in types; anything with "block" in the name is a
# genuine dependency, everything else (Relates, Duplicate, Cloners, ...)
# is treated as a looser relation.
def _link_kind_for_type(type_name: str) -> str:
    return "depends_on" if "block" in type_name.lower() else "relates_to"


def _content_hash(raw: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(raw, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def adf_to_text(node: Any) -> str:
    """Flattens an Atlassian Document Format node (Jira v3's rich-text
    shape for description/comment bodies) into plain text — just enough to
    let link-mention regexes scan it and to give humans a readable
    get_content() body; not a full ADF renderer."""
    if not isinstance(node, dict):
        return ""
    parts = []
    if node.get("type") == "text":
        parts.append(str(node.get("text", "")))
    for child in node.get("content", []) or []:
        parts.append(adf_to_text(child))
    return " ".join(p for p in parts if p)


def map_project(raw: dict[str, Any]) -> SourceContainer:
    return SourceContainer(
        id=raw["key"],
        name=raw["name"],
        kind="PROJECT",
        parent_id=None,
        native_id=raw["key"],
        attributes={"description": raw.get("description", ""), "url": raw.get("url", "")},
    )


def map_issue(raw: dict[str, Any]) -> SourceObject:
    """`raw` is the flattened issue dict live.py/fixture.py build — see
    their own `key`/`project_key`/`parent_key`/`summary`/`issue_type`/
    `status`/`assignee`/`description_text`/`url` fields."""
    kind = ISSUE_TYPE_TO_KIND.get(raw["issue_type"], "WORK_ITEM")
    parent_native_id = raw.get("parent_key") or raw["project_key"]
    return SourceObject(
        native_id=raw["key"],
        kind=kind,
        name=raw["summary"],
        parent_native_id=parent_native_id,
        attributes={
            "status": raw.get("status"),
            "assignee": raw.get("assignee"),
            "url": raw.get("url", ""),
            "labels": raw.get("labels", []),
            # Deliberately not description_text — ADR-003 fetches full
            # content on-demand via get_content() rather than eagerly
            # duplicating it into every synced node's attributes.
        },
        source_version=str(raw.get("updated", "")),
        content_hash=_content_hash(raw),
    )


def map_tombstone(native_id: str, kind: str) -> SourceObject:
    return SourceObject(native_id=native_id, kind=kind, name="", deleted=True)


def map_comment(raw: dict[str, Any], issue_key: str) -> SourceObject:
    body_text = raw.get("body_text", "") or ""
    snippet = body_text[:60] + ("…" if len(body_text) > 60 else "")
    return SourceObject(
        native_id=f"COMMENT-{raw['id']}",
        kind="COMMENT",
        name=snippet or "(comment)",
        parent_native_id=issue_key,
        attributes={"author": raw.get("author"), "url": raw.get("url", "")},
        content_hash=_content_hash(raw),
    )


def map_content(native_id: str, raw_issue: dict[str, Any]) -> SourceContent:
    return SourceContent(
        native_id=native_id,
        version=str(raw_issue.get("updated", "")),
        mime_type="text/plain",
        text=raw_issue.get("description_text", ""),
        uri=raw_issue.get("url", ""),
    )


def map_comment_content(native_id: str, raw_comment: dict[str, Any]) -> SourceContent:
    return SourceContent(
        native_id=native_id,
        mime_type="text/plain",
        text=raw_comment.get("body_text", ""),
        uri=raw_comment.get("url", ""),
    )


def _links_from_text(native_id: str, text: str) -> list[SourceLink]:
    links = [
        SourceLink(from_native_id=native_id, target_ref=f"AB#{m.group(1)}", link_kind="mentions")
        for m in _MENTION_PATTERN.finditer(text)
    ]
    links += [
        SourceLink(from_native_id=native_id, target_ref=f"PR-{m.group(1)}", link_kind="mentions")
        for m in _PR_MENTION_PATTERN.finditer(text)
    ]
    links += [
        SourceLink(
            from_native_id=native_id, target_ref=f"{m.group(1)}#{m.group(2)}", link_kind="mentions"
        )
        for m in _GITHUB_CROSS_REPO_REF_PATTERN.finditer(text)
    ]
    return links


def map_links(raw_issue: dict[str, Any]) -> list[SourceLink]:
    native_id = raw_issue["key"]
    links: list[SourceLink] = []

    for link in raw_issue.get("issuelinks", []):
        target_key = link.get("target_key")
        if not target_key:
            continue
        links.append(
            SourceLink(
                from_native_id=native_id,
                target_ref=target_key,
                link_kind=_link_kind_for_type(link.get("type_name", "")),  # type: ignore[arg-type]
            )
        )

    links += _links_from_text(native_id, raw_issue.get("description_text", "") or "")
    return links


def map_comment_links(raw_comment: dict[str, Any], issue_key: str) -> list[SourceLink]:
    native_id = f"COMMENT-{raw_comment['id']}"
    return _links_from_text(native_id, raw_comment.get("body_text", "") or "")


def map_acl(raw: dict[str, Any]) -> ACLReference:
    return ACLReference(native_id=raw["native_id"], acl_ref=raw["acl_ref"])
