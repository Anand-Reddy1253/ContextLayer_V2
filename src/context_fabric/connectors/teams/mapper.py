"""Microsoft Teams payload -> domain/ type mapping.

The only module in connectors/teams/ allowed to know Microsoft Graph's
REST API JSON shape (docs/CONNECTORS.md "Adding a new connector"). Native
hierarchy: Channel -> Message -> Reply, all within one Team named by
config.team_id (docs/CONNECTORS.md "Native hierarchies") — a Team itself
isn't discovered/listed here since a connection is already scoped to
exactly one, the same way an ADO connection is scoped to one org.

The COMMUNICATION capability (configs/capabilities.yaml) exists for
exactly this connector: "what was actually discussed," not just what got
decided in a work item or doc — added at the user's explicit request
after they picked "communication channel" as the single most useful piece
of business context.
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


def map_channel(raw: dict[str, Any]) -> SourceContainer:
    return SourceContainer(
        id=raw["id"],
        name=raw.get("displayName", raw["id"]),
        kind="CHANNEL",
        parent_id=None,
        native_id=raw["id"],
        attributes={"description": raw.get("description", ""), "url": raw.get("webUrl", "")},
    )


def map_message(raw: dict[str, Any]) -> SourceObject:
    """`raw` is the flattened message dict live.py/fixture.py build:
    `{"id", "channel_id", "author", "created", "body_text", "url"}` —
    `body_text` already stripped of HTML by the caller (Graph's chatMessage
    body is HTML)."""
    body = raw.get("body_text", "") or ""
    snippet = body[:60] + ("…" if len(body) > 60 else "")
    return SourceObject(
        native_id=raw["id"],
        kind="MESSAGE",
        name=snippet or "(message)",
        parent_native_id=raw["channel_id"],
        attributes={
            "author": raw.get("author"),
            "created": raw.get("created"),
            "url": raw.get("url", ""),
            # channel_id: not for display — it's what a native Teams MCP
            # tool's get_channel_messages call needs alongside native_id
            # to fetch this message directly (docs/BENCHMARK.md's locator
            # research: a URL alone isn't a native tool's input shape).
            "channel_id": raw["channel_id"],
            # Deliberately not body_text — ADR-003 fetches full content
            # on-demand via get_content() rather than eagerly duplicating
            # it into every synced node's attributes.
        },
        source_version=raw.get("created"),
        content_hash=_content_hash(raw),
    )


def map_reply(raw: dict[str, Any]) -> SourceObject:
    """Same flattened shape as map_message plus `message_id` (the
    top-level message this replies to)."""
    body = raw.get("body_text", "") or ""
    snippet = body[:60] + ("…" if len(body) > 60 else "")
    return SourceObject(
        native_id=raw["id"],
        kind="MESSAGE_REPLY",
        name=snippet or "(reply)",
        parent_native_id=raw["message_id"],
        attributes={
            "author": raw.get("author"),
            "created": raw.get("created"),
            "url": raw.get("url", ""),
            "channel_id": raw["channel_id"],
        },
        source_version=raw.get("created"),
        content_hash=_content_hash(raw),
    )


def map_tombstone(native_id: str, kind: str) -> SourceObject:
    return SourceObject(native_id=native_id, kind=kind, name="", deleted=True)


def map_content(native_id: str, raw: dict[str, Any]) -> SourceContent:
    return SourceContent(
        native_id=native_id,
        version=raw.get("created"),
        mime_type=raw.get("content_type") or "text/plain",
        text=raw.get("body_text", ""),
        uri=raw.get("url", ""),
    )


def map_links(raw: dict[str, Any]) -> list[SourceLink]:
    """AB#/PR-/GitHub-cross-repo/Jira-key mentions in a message or reply's
    text — same cross-reference convention every other connector's free
    text is already scanned for (docs/CONNECTORS.md "Link extraction")."""
    native_id = raw["id"]
    text = raw.get("body_text", "") or ""
    # A chat message is the weakest place a reference can appear — shared
    # patterns, but location="comment" keeps it a plain MENTIONS edge.
    return extract_cross_references(native_id, text, location="comment", where_label="chat message")


def map_acl(raw: dict[str, Any]) -> ACLReference:
    return ACLReference(native_id=raw["native_id"], acl_ref=raw["acl_ref"])
