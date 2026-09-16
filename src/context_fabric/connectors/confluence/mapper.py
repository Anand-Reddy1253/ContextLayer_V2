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

from context_fabric.connectors.confluence import page_properties, storage_format
from context_fabric.connectors.cross_references import (
    CONFIDENCE_BY_LOCATION,
    extract_cross_references,
)
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
        attributes={
            "key": raw.get("key", ""),
            "url": raw.get("url", ""),
            # global | personal — from the same /spaces payload, no new
            # API call, lets a caller exclude personal-space noise.
            "type": raw.get("type", ""),
        },
        description=description_value[:512] or None,
    )


def _classified_page_attributes(raw: dict[str, Any]) -> dict[str, Any]:
    """page_type/page_properties/schema_completeness — a direct table
    parse of the page's own Page Properties macro plus label/title-based
    template classification (connectors/confluence/page_properties.py),
    never an LLM call. A page whose body fails to parse, or has no such
    macro, classifies as page_type=None rather than guessing."""
    body = raw.get("body", "") or ""
    root = storage_format.parse_xml(body) if body else None
    props = page_properties.extract_page_properties(root) if root is not None else {}
    classification = page_properties.classify_page(
        title=raw.get("title", ""), labels=raw.get("labels", []), page_properties=props
    )
    return page_properties.page_type_attributes(classification, props)


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
            # From already-fetched data, no new API call: Confluence's
            # own page status doubles as an archived flag.
            "archived": raw.get("status") == "archived",
            # Data capture only, no enforcement yet (authorization/
            # doesn't exist — see connectors/confluence/live.py's
            # _fetch_restrictions docstring).
            "restricted": raw.get("restricted", False),
            "restriction_subjects": raw.get("restriction_subjects", []),
            **_classified_page_attributes(raw),
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


def map_person(account_id: str, display_name: str | None, *, parent_native_id: str) -> SourceObject:
    """A Confluence-scoped author/commenter (docs/CONNECTORS.md — Tier 1).
    Deliberately Confluence-only, keyed on Confluence's own account_id:
    cross-connector identity resolution (a Person supernode with SAME_AS
    to GitHubLogin/ADOUser) is a separate, larger effort — this node is a
    real subset of that future work, not a conflicting design. Same
    account_id seen from two different spaces/pages merges into one node
    (NodeRepository upsert keys on technical identity, not parent) — the
    last space/page processed each sync "wins" for parent_native_id, an
    accepted simplification (same spirit as the ADO test-hierarchy
    fallback elsewhere in this codebase)."""
    return SourceObject(
        native_id=account_id,
        kind="PERSON",
        name=display_name or account_id,
        parent_native_id=parent_native_id,
        attributes={"account_id": account_id},
    )


def map_label(name: str, *, parent_native_id: str) -> SourceObject:
    """A Confluence label as its own node (docs/CONNECTORS.md — "what to
    also extract") rather than a plain string on the PAGE — lets a caller
    traverse "everything tagged payments" as a real graph query. native_id
    is the label text itself, stable and already unique per Confluence's
    own model."""
    return SourceObject(
        native_id=name,
        kind="LABEL",
        name=name,
        parent_native_id=parent_native_id,
        attributes={},
    )


def map_blog_post(raw: dict[str, Any]) -> SourceObject:
    """Confluence's own /blogposts entity — structurally parallel to a
    page (same storage-format body, same author/labels), used for
    announcements/decision broadcasts rather than living documentation
    (docs/CONNECTORS.md — "what to also extract")."""
    return SourceObject(
        native_id=f"BLOG-{raw['id']}",
        kind="BLOG_POST",
        name=raw.get("title", ""),
        parent_native_id=str(raw["spaceId"]),
        attributes={
            "status": raw.get("status"),
            "url": raw.get("url", ""),
            "labels": raw.get("labels", []),
            "author_id": raw.get("authorId", ""),
            "created_at": raw.get("createdAt", ""),
            **_classified_page_attributes(raw),
        },
        source_version=str(raw.get("version", "")),
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


def extract_structured_links(
    native_id: str, body: str, *, location: str = "page_body"
) -> list[SourceLink]:
    """The Tier 2 replacement for map_links_from_text's raw whole-string
    regex scan (docs/CONNECTORS.md): walks the parsed storage-format tree
    once for `ac:link`/`ri:page` (LINKS_TO — including the title+space
    variant a plain regex could never resolve), `ri:user` mentions,
    `ac:name="jira"` macros (the JQL-filter variant is explicitly
    skipped — a filter has no single resolvable target), and
    `ac:name="include"`/`excerpt-include` (TRANSCLUDES). Whatever's left
    over as plain text still goes through the *existing*
    extract_cross_references unchanged — macro internals are excluded
    from that text so a macro's own parameter values (a page id, a Jira
    key already handled structurally above) aren't re-scanned as if they
    were prose, which would otherwise double-extract the same reference.

    Falls back to map_links_from_text's old raw-string scan whole-body
    when the body isn't well-formed XML even after storage_format's
    namespace-wrapping — a malformed page must never lose reference
    extraction entirely, just the structural half of it.
    """
    where_label = "page body" if location == "page_body" else location.replace("_", " ")
    confidence = CONFIDENCE_BY_LOCATION.get(location, 0.85)
    root = storage_format.parse_xml(body)
    if root is None:
        return map_links_from_text(native_id, body, location=location)
    parsed = storage_format.analyze(root)

    links: list[SourceLink] = []

    def _page_ref_target(ref: storage_format.PageLinkRef) -> str | None:
        if ref.content_id is not None:
            return f"CONFPAGE-{ref.content_id}"
        if ref.space_key and ref.title:
            return f"CONFTITLE:{ref.space_key}:{ref.title}"
        return None

    for ref in parsed.page_links:
        target_ref = _page_ref_target(ref)
        if target_ref is None or target_ref == f"CONFPAGE-{native_id}":
            continue
        links.append(
            SourceLink(
                from_native_id=native_id,
                target_ref=target_ref,
                link_kind="links_to",
                confidence=confidence,
                evidence=f'Found a Confluence page-link macro in the {where_label}: '
                f'"{ref.title or ref.content_id}"',
            )
        )

    for account_id in parsed.user_mentions:
        links.append(
            SourceLink(
                from_native_id=native_id,
                target_ref=f"CONFUSER:{account_id}",
                link_kind="mentions",
                confidence=confidence,
                evidence=f"Found a Confluence user-mention macro in the {where_label}",
            )
        )

    for jira in parsed.jira_macros:
        if jira.is_jql or not jira.key:
            continue
        links.append(
            SourceLink(
                from_native_id=native_id,
                target_ref=jira.key,
                link_kind="mentions",
                confidence=confidence,
                evidence=f'Found a Confluence Jira macro in the {where_label}: "{jira.key}"',
            )
        )

    for ref in parsed.includes:
        target_ref = _page_ref_target(ref)
        if target_ref is None or target_ref == f"CONFPAGE-{native_id}":
            continue
        links.append(
            SourceLink(
                from_native_id=native_id,
                target_ref=target_ref,
                link_kind="transcludes",
                confidence=confidence,
                evidence=f'Found a Confluence include macro in the {where_label}: '
                f'"{ref.title or ref.content_id}"',
            )
        )

    links.extend(
        extract_cross_references(
            native_id,
            parsed.plain_text,
            location=location,
            where_label=where_label,
            skip_ref=lambda ref: ref == f"CONFPAGE-{native_id}",
        )
    )
    return links


def map_page_relationship_links(
    native_id: str,
    *,
    space_native_id: str | None = None,
    author_account_id: str | None = None,
    label_names: list[str] | None = None,
) -> list[SourceLink]:
    """The Tier 1 edges emitted from a PAGE/BLOG_POST's own get_links()
    call — IN_SPACE, AUTHORED_BY, HAS_LABEL. All vendor-declared
    structure, never inferred, so every one is confidence 1.0
    (auto-confirms past link_extraction.py's _AUTO_CONFIRM_THRESHOLD, same
    treatment as the structural CONTAINS hierarchy) rather than landing in
    the human review queue.

    COMMENTED_ON is deliberately not here — comments aren't fetched yet
    when a page's own get_links() runs (synchronization/orchestrator.py's
    BFS extracts a node's links immediately after upserting it, before
    ever calling list_children on it to discover comments); see
    map_comment_relationship_links below, called once each comment is
    actually processed."""
    links: list[SourceLink] = []
    if space_native_id:
        links.append(
            SourceLink(
                from_native_id=native_id,
                target_ref=f"CONFSPACE:{space_native_id}",
                link_kind="in_space",
                confidence=1.0,
                evidence="Confluence's own space membership",
            )
        )
    if author_account_id:
        links.append(
            SourceLink(
                from_native_id=native_id,
                target_ref=f"CONFUSER:{author_account_id}",
                link_kind="authored_by",
                confidence=1.0,
                evidence="Confluence's own page/blog-post authorship",
            )
        )
    for name in label_names or []:
        links.append(
            SourceLink(
                from_native_id=native_id,
                target_ref=f"CONFLABEL:{name}",
                link_kind="has_label",
                confidence=1.0,
                evidence="Confluence's own page label",
            )
        )
    return links


def map_comment_relationship_links(
    native_id: str, *, author_account_id: str | None
) -> list[SourceLink]:
    """COMMENTED_ON — PERSON -> COMMENT (who left this specific comment,
    not "who commented on the page" — the page is one CONTAINS hop away
    from the comment already, so this stays precise rather than
    collapsing every comment on a page into the same edge). Emitted from
    the comment's own get_links() call, where the author is already
    known, unlike the page's."""
    if not author_account_id:
        return []
    return [
        SourceLink(
            from_native_id=native_id,
            target_ref=f"CONFUSER:{author_account_id}",
            link_kind="commented_on",
            confidence=1.0,
            evidence="Confluence's own comment authorship",
            # The edge belongs pointing PERSON -> COMMENT, not the other
            # way — reverse tells link_extraction.py to flip src/dst even
            # though `native_id` (the comment) is the node this call is
            # for.
            reverse=True,
        )
    ]


def map_acl(raw: dict[str, Any]) -> ACLReference:
    return ACLReference(native_id=raw["native_id"], acl_ref=raw["acl_ref"])
