"""Confluence storage-format (XHTML) body parsing — the piece that used to
not exist at all (docs/CONNECTORS.md). Before this module, every
cross-reference was found by regex-scanning the raw body string
(cross_references.py's REFERENCE_PATTERNS), which can only ever recognize
inline text conventions ("AB#123") and can't tell a `jira` macro's real
`key` parameter from its `jqlQuery` variant, or a same-id
`ri:content-id` link from a cross-space `ri:page` title+space reference.

Uses stdlib `xml.etree.ElementTree` — no new dependency. Confluence's API
returns a body *fragment* using `ac:`/`ri:` prefixes with no namespace
declaration of their own (they're bound at the full-document level on
Confluence's own servers, not in what the REST API hands back), which
`ElementTree.fromstring` rejects outright as an undefined-prefix error.
Wrapped in a synthetic root that declares them before parsing — the
namespace URIs are arbitrary placeholders (never validated against
Atlassian's real schema, this module only needs well-formed XML to walk),
just held constant so `{ac}structured-macro`-shaped tags are stable to
match against.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from xml.etree.ElementTree import Element, ParseError, fromstring

import structlog

logger = structlog.get_logger()

AC_NS = "ac"
RI_NS = "ri"
_WRAPPER = f'<root xmlns:{AC_NS}="ac" xmlns:{RI_NS}="ri">{{body}}</root>'


def qualified_tag(ns: str, local: str) -> str:
    """Public — page_properties.py's Page Properties table parser needs
    this too, to match `ac:structured-macro` the same way this module
    does, over the same already-parsed tree (storage_format.parse_xml)."""
    return f"{{{ns}}}{local}"


@dataclass
class PageLinkRef:
    """A `ri:page` reference — either resolvable directly by Confluence's
    own page id, or only by title+space (a cross-space link that never
    carries the id)."""

    content_id: str | None = None
    space_key: str | None = None
    title: str | None = None


@dataclass
class JiraMacroRef:
    """One `ac:name="jira"` macro. `key` is set for the single-issue
    variant; `is_jql` marks the filter variant (a `jqlQuery` parameter,
    no single resolvable target) so callers can skip it explicitly rather
    than mis-extracting a "key" that was never there."""

    key: str | None
    is_jql: bool


@dataclass
class ParsedBody:
    page_links: list[PageLinkRef] = field(default_factory=list)
    user_mentions: list[str] = field(default_factory=list)  # account ids
    jira_macros: list[JiraMacroRef] = field(default_factory=list)
    includes: list[PageLinkRef] = field(default_factory=list)  # include/excerpt-include targets
    # Everything else — running text, raw <a href> URLs, and any macro's
    # human-readable label — with recognized-macro *parameter* values
    # excluded so they aren't re-scanned by extract_cross_references as if
    # they were prose (a jira macro's own key, already handled above,
    # would otherwise also show up as a bare Jira-key-shaped text match).
    plain_text: str = ""


def local_name(tag: str) -> str:
    """Strips the `{namespace}` prefix ElementTree tags carry after
    parsing — comparing against a bare local name is more robust here
    than re-deriving the qualified name at every call site. Public for
    the same reason as qualified_tag above."""
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _macro_param(macro: Element, name: str) -> str | None:
    for param in macro.findall(qualified_tag(AC_NS, "parameter")):
        if param.get(qualified_tag(AC_NS, "name")) == name:
            return (param.text or "").strip() or None
    return None


def _ri_page_from(el: Element) -> PageLinkRef | None:
    """`<ri:page ri:content-title="..." ri:space-key="..."/>` (or, less
    commonly, `ri:content-id`) — found anywhere under `el`, not just as a
    direct child: under an `ac:link` it is one, but the include/
    transclusion macros' own `page` parameter nests it one level deeper
    (`ac:structured-macro > ac:parameter > ri:page`), which a plain
    `.find()` (immediate children only) would miss entirely."""
    ri_page = el.find(f".//{qualified_tag(RI_NS, 'page')}")
    if ri_page is None:
        return None
    content_id = ri_page.get(qualified_tag(RI_NS, "content-id"))
    title = ri_page.get(qualified_tag(RI_NS, "content-title"))
    space_key = ri_page.get(qualified_tag(RI_NS, "space-key"))
    if content_id is None and title is None:
        return None
    return PageLinkRef(content_id=content_id, space_key=space_key, title=title)


def parse_xml(body: str) -> Element | None:
    """The shared parse step: wraps `body` in a namespace-declaring root
    and parses it. Returns None (never raises) when the body isn't
    well-formed XML even after wrapping — storage format isn't always
    strictly valid, and a single malformed page must never fail sync.
    Exposed separately (not just as an internal step of
    parse_storage_format below) so page_properties.py's Page Properties
    table parser can walk the same tree instead of re-parsing the body a
    second time — both run once per page, from mapper.py."""
    if not body:
        return fromstring(_WRAPPER.format(body=""))
    try:
        return fromstring(_WRAPPER.format(body=body))
    except ParseError as exc:
        logger.warning("confluence.storage_format_parse_failed", error=str(exc))
        return None


def analyze(root: Element) -> ParsedBody:
    """Walks an already-parsed tree (parse_xml's result) for links,
    mentions, macros, and plain text. Split from parse_storage_format
    below only so a root already produced by parse_xml can be reused."""
    result = ParsedBody()
    text_parts: list[str] = []
    # Element ids (by identity) whose subtree is a recognized macro's
    # internals — excluded from the plain-text walk below so a macro's own
    # parameter values (a page title, a Jira key already captured
    # structurally) aren't also scanned as prose.
    consumed: set[int] = set()

    for link in root.iter(qualified_tag(AC_NS, "link")):
        ref = _ri_page_from(link)
        if ref is not None:
            result.page_links.append(ref)
            consumed.add(id(link))
            continue
        ri_user = link.find(qualified_tag(RI_NS, "user"))
        if ri_user is not None:
            account_id = ri_user.get(qualified_tag(RI_NS, "account-id"))
            if account_id:
                result.user_mentions.append(account_id)
            consumed.add(id(link))

    for macro in root.iter(qualified_tag(AC_NS, "structured-macro")):
        name = macro.get(qualified_tag(AC_NS, "name"))
        if name == "jira":
            key = _macro_param(macro, "key")
            jql = _macro_param(macro, "jqlQuery")
            result.jira_macros.append(JiraMacroRef(key=key, is_jql=jql is not None and key is None))
            consumed.add(id(macro))
        elif name in ("include", "excerpt-include"):
            ref = _ri_page_from(macro)
            if ref is not None:
                result.includes.append(ref)
            consumed.add(id(macro))
        elif name == "details":
            # The Page Properties table — page_properties.py parses this
            # macro's own subtree separately (same already-parsed root,
            # from mapper.py). Consumed here only so its cell text (a
            # status word, a decision summary) doesn't also leak into
            # plain_text and get re-scanned as prose.
            consumed.add(id(macro))

    def walk_text(el: Element) -> None:
        if id(el) in consumed:
            # Still descend into an <ac:link>'s own body text (the link's
            # human-readable label, e.g. "see the design doc") — only the
            # ri:page/ri:user *reference* itself is consumed, not the
            # element's visible text.
            if local_name(el.tag) != "link":
                return
        if el.text:
            text_parts.append(el.text)
        for child in el:
            walk_text(child)
            if child.tail:
                text_parts.append(child.tail)

    walk_text(root)
    result.plain_text = re.sub(r"\s+", " ", " ".join(text_parts)).strip()
    return result


def parse_storage_format(body: str) -> ParsedBody | None:
    """parse_xml + analyze in one call — the common case for a caller
    that only needs links/mentions/macros, not the raw tree itself (see
    parse_xml's docstring for why a caller needing *both* this and
    page_properties.py's table parse should call parse_xml once and pass
    the resulting root to both instead)."""
    root = parse_xml(body)
    return analyze(root) if root is not None else None
