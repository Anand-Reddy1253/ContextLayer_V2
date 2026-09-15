"""Confluence Cloud payload -> domain/ type mapping.

The only module in connectors/confluence/ allowed to know Confluence's
REST API v2 JSON shape (docs/CONNECTORS.md "Adding a new connector").
Native hierarchy: Space -> Page -> child Page, with Attachments and
Comments as leaves parented by the page they belong to.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from context_fabric.connectors.cross_references import extract_cross_references
from context_fabric.domain.connector_types import (
    ACLReference,
    SourceContainer,
    SourceContent,
    SourceLink,
    SourceObject,
)


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
    parent_native_id = str(raw["parentId"]) if raw.get("parentId") else str(raw["spaceId"])
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
            "created_at": raw.get("createdAt", ""),
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


def map_links_from_text(
    native_id: str, text: str, *, location: str = "page_body"
) -> list[SourceLink]:
    """Cross-references out of a page or comment body. Patterns are shared
    (connectors/cross_references.py) so this connector recognizes the same
    shapes as every other. Page bodies default to location="page_body",
    which types the resulting edge as SPECIFIED_BY rather than a bare
    mention — a spec page naming a work item is documenting it."""
    return extract_cross_references(
        native_id,
        text,
        location=location,
        where_label="page body",
        # A page linking to itself isn't a real edge.
        skip_ref=lambda ref: ref == f"CONFPAGE-{native_id}",
    )


def map_acl(raw: dict[str, Any]) -> ACLReference:
    return ACLReference(native_id=raw["native_id"], acl_ref=raw["acl_ref"])
