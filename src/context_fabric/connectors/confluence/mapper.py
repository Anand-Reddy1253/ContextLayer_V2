"""Confluence Cloud payload -> domain/ type mapping.

The only module in connectors/confluence/ allowed to know Confluence's
REST API v2 JSON shape (docs/CONNECTORS.md "Adding a new connector").
Native hierarchy: Space -> Page -> child Page, with Attachments and
Comments as leaves parented by the page they belong to.
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

_MENTION_PATTERN = re.compile(r"AB#(\d+)")
_PR_MENTION_PATTERN = re.compile(r"\bPR-(\d+)\b")
# GitHub's own cross-repo issue/PR reference syntax ("owner/repo#42") —
# fully qualified, so unlike GitHub's own same-repo "#NN" shorthand
# (meaningless without a repo to resolve against, which a Confluence page
# doesn't have), this is directly resolvable on its own.
_GITHUB_CROSS_REPO_REF_PATTERN = re.compile(r"\b([\w.-]+/[\w.-]+)#(\d+)\b")
# Jira's own issue-key shape ("PROJ-123") — see
# synchronization/link_extraction.py's LINK_PATTERNS for why this is
# resolvable on its own without a repo/instance qualifier.
_JIRA_KEY_PATTERN = re.compile(r"\b([A-Z][A-Z0-9]{1,9}-\d+)\b")
# Confluence's own internal page-to-page link macro
# (`<ac:link><ri:page ri:content-id="12345" /></ac:link>`) — a real,
# human-placed cross-reference between two pages, distinct from the
# parent/child CONTAINS hierarchy already captured structurally. Only
# `ri:content-id` is matched (a direct, reliable native_id), not
# `ri:content-title` (would need name-based resolution, a different
# mechanism than the native_id-based LINK_PATTERNS this project already
# has — out of scope for this pass).
_INTERNAL_PAGE_LINK_PATTERN = re.compile(r'ri:content-id="(\d+)"')


def _snippet(text: str, match_start: int, match_end: int, *, radius: int = 80) -> str:
    """The window of text around a regex match, shown to a Proposed
    Links reviewer as evidence for why an edge was proposed."""
    start = max(0, match_start - radius)
    end = min(len(text), match_end + radius)
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(text) else ""
    return f"{prefix}{text[start:end].strip()}{suffix}"


def _content_hash(raw: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(raw, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def map_space(raw: dict[str, Any]) -> SourceContainer:
    # v2's description-format=plain shape: {"plain": {"value": "...", ...}}
    # — None (the whole key, not just the value) when the space has no
    # description set, confirmed against the real live API.
    description_value = ((raw.get("description") or {}).get("plain") or {}).get("value") or ""
    return SourceContainer(
        id=str(raw["id"]),
        name=raw["name"],
        kind="SPACE",
        parent_id=None,
        native_id=str(raw["id"]),
        attributes={"key": raw.get("key", ""), "url": raw.get("url", "")},
        description=description_value[:512] or None,
    )


def map_page(raw: dict[str, Any]) -> SourceObject:
    parent_native_id = (
        str(raw["parentId"]) if raw.get("parentId") else str(raw["spaceId"])
    )
    return SourceObject(
        native_id=str(raw["id"]),
        kind="PAGE",
        name=raw["title"],
        parent_native_id=parent_native_id,
        attributes={
            "status": raw.get("status"),
            "url": raw.get("url", ""),
            "labels": raw.get("labels", []),
            "author_id": raw.get("authorId", ""),
            "updated_at": raw.get("updatedAt", ""),
            # Deliberately not the page body — it's HTML and can be
            # large; ADR-003 fetches full content on-demand via
            # get_content()/map_page_content() rather than eagerly
            # duplicating it into every synced node's attributes.
        },
        source_version=str(raw.get("version", "")),
        content_hash=_content_hash(raw),
    )


def map_attachment(raw: dict[str, Any]) -> SourceObject:
    return SourceObject(
        native_id=f"ATT-{raw['id']}",
        kind="ATTACHMENT",
        name=raw["title"],
        parent_native_id=str(raw["pageId"]),
        attributes={
            "media_type": raw.get("mediaType"),
            "file_size": raw.get("fileSize"),
            "url": raw.get("url", ""),
        },
        content_hash=_content_hash(raw),
    )


def map_comment(raw: dict[str, Any]) -> SourceObject:
    body = raw.get("body", "") or ""
    snippet = body[:60] + ("…" if len(body) > 60 else "")
    return SourceObject(
        native_id=f"COMMENT-{raw['id']}",
        kind="COMMENT",
        name=snippet or "(comment)",
        parent_native_id=str(raw["pageId"]),
        attributes={"author": raw.get("author"), "url": raw.get("url", "")},
        content_hash=_content_hash(raw),
    )


def map_tombstone(native_id: str, kind: str) -> SourceObject:
    return SourceObject(native_id=native_id, kind=kind, name="", deleted=True)


def map_page_content(native_id: str, raw_page: dict[str, Any]) -> SourceContent:
    return SourceContent(
        native_id=native_id,
        version=str(raw_page.get("version", "")),
        mime_type="text/html",
        text=raw_page.get("body", ""),
        uri=raw_page.get("url", ""),
    )


def map_comment_content(native_id: str, raw_comment: dict[str, Any]) -> SourceContent:
    return SourceContent(
        native_id=native_id,
        mime_type="text/html",
        text=raw_comment.get("body", ""),
        uri=raw_comment.get("url", ""),
    )


def map_links_from_text(native_id: str, text: str) -> list[SourceLink]:
    """AB#123 (Azure Boards work item) and PR-42 (pull request) style
    mentions in page/comment body text — the same cross-reference
    convention already recognized from GitHub commit messages and ADO
    descriptions (docs/CONNECTORS.md "Link extraction")."""
    links = [
        SourceLink(
            from_native_id=native_id,
            target_ref=f"AB#{m.group(1)}",
            link_kind="mentions",
            evidence=f'Found in the page body: "{_snippet(text, m.start(), m.end())}"',
        )
        for m in _MENTION_PATTERN.finditer(text)
    ]
    links += [
        SourceLink(
            from_native_id=native_id,
            target_ref=f"PR-{m.group(1)}",
            link_kind="mentions",
            evidence=f'Found in the page body: "{_snippet(text, m.start(), m.end())}"',
        )
        for m in _PR_MENTION_PATTERN.finditer(text)
    ]
    links += [
        SourceLink(
            from_native_id=native_id,
            target_ref=f"{m.group(1)}#{m.group(2)}",
            link_kind="mentions",
            evidence=f'Found in the page body: "{_snippet(text, m.start(), m.end())}"',
        )
        for m in _GITHUB_CROSS_REPO_REF_PATTERN.finditer(text)
    ]
    links += [
        SourceLink(
            from_native_id=native_id,
            target_ref=m.group(1),
            link_kind="mentions",
            evidence=f'Found in the page body: "{_snippet(text, m.start(), m.end())}"',
        )
        for m in _JIRA_KEY_PATTERN.finditer(text)
    ]
    links += [
        SourceLink(
            from_native_id=native_id,
            target_ref=f"CONFPAGE-{m.group(1)}",
            link_kind="relates_to",
            evidence="Confluence's own internal page-link macro (ri:content-id) in the page body.",
        )
        for m in _INTERNAL_PAGE_LINK_PATTERN.finditer(text)
        if m.group(1) != native_id  # a page linking to itself isn't a real edge
    ]
    return links


def map_acl(raw: dict[str, Any]) -> ACLReference:
    return ACLReference(native_id=raw["native_id"], acl_ref=raw["acl_ref"])
