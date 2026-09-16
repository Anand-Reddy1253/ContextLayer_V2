"""Confluence Cloud live-mode connector, following the same fast-tracked
pattern as connectors/azure_devops/live.py and connectors/github/live.py.

Reuses connectors/confluence/mapper.py unchanged — the fixture JSON
shapes were modeled on Confluence's real REST API v2 response shapes
(`{"id", "title", "spaceId", "parentId", "version": {"number": ...}}`
etc., flattened slightly for the fixture files).

Auth: Confluence Cloud uses Basic auth with the account email + an API
token (not a single opaque PAT like ADO/GitHub) — the email isn't a
secret, so it lives in config.email alongside config.site_url, while the
API token is the connection's single encrypted `credential`, consistent
with how org_url/org are plain config next to an encrypted PAT/token for
the other two connectors.

Entity types (docs/CONNECTORS.md "Entity type selection"): which of
pages / attachments / comments this connector instance fetches is chosen
per-connection at creation time (config.entity_types) — see ENTITY_TYPES
below. Spaces themselves are always listed as containers (the pick-able
unit via config.selected_containers, docs/UI.md "Connectors" picker) —
without at least "pages" selected, a space's children are empty, since
attachments/comments both hang off pages.

Known simplifications:
  - get_acl_reference returns {"space": <key>} — no real Confluence
    permission-API check.
  - get_changes returns an always-empty page — no incremental delta feed
    implemented yet (would need Confluence's audit/trash APIs).
  - Only "footer" (top-level, non-inline) comments are fetched — inline
    comments anchored to specific text selections are a separate API
    surface, out of scope for this pass.

Every HTTP call goes through LiveConnectorBase.call_with_retry and
raise_for_status_category (401/403 -> AuthError, 404 -> NotFound, 429 ->
RateLimited, 5xx -> Transient, other 4xx -> Permanent).
"""

from __future__ import annotations

import base64
from typing import Any, ClassVar
from urllib.parse import urlsplit, urlunsplit

import httpx
import structlog

from context_fabric.connectors.base import DEFAULT_TIMEOUT, LiveConnectorBase
from context_fabric.connectors.confluence import mapper
from context_fabric.domain.connector_types import (
    ACLReference,
    ChangePage,
    Page,
    SourceContainer,
    SourceContent,
    SourceLink,
    SourceObject,
)
from context_fabric.domain.errors import AuthError, NotFound, Permanent

logger = structlog.get_logger()

_API_VERSION_PATH = "/wiki/api/v2"
_PAGE_LIMIT = 100


def _normalize_site_url(site_url: str) -> str:
    """Strips anything beyond the bare site origin — a URL copied from
    the browser while inside a space or page (e.g.
    "https://acme.atlassian.net/wiki/spaces/TALENT/overview") carries
    the whole /wiki/... path along, and this connector appends its own
    "/wiki/api/v2/..." prefix, so a stray path here would double up."""
    parts = urlsplit(site_url.strip().rstrip("/"))
    return urlunsplit((parts.scheme, parts.netloc, "", "", ""))


class ConfluenceLiveConnector(LiveConnectorBase):
    source_system = "confluence"

    ENTITY_TYPES: ClassVar[dict[str, str]] = {
        "pages": "Pages",
        "attachments": "Attachments",
        "comments": "Comments",
        "people": "Authors & commenters",
        "blogposts": "Blog posts",
    }

    def __init__(
        self,
        site_url: str,
        *,
        email: str,
        api_token: str,
        timeout: httpx.Timeout = DEFAULT_TIMEOUT,
        max_attempts: int = 5,
        entity_types: list[str] | None = None,
        selected_containers: list[str] | None = None,
    ) -> None:
        site_url = _normalize_site_url(site_url)
        token = base64.b64encode(f"{email}:{api_token}".encode()).decode("ascii")
        headers = {"Authorization": f"Basic {token}", "Accept": "application/json"}
        super().__init__(
            f"{site_url}{_API_VERSION_PATH}",
            timeout=timeout,
            headers=headers,
            max_attempts=max_attempts,
        )
        self._entity_types = set(entity_types) if entity_types else set(self.ENTITY_TYPES)
        # Which spaces to actually sync (key or id) — None means "all of
        # them" (docs/UI.md "Connectors" space picker).
        self._selected_containers = set(selected_containers) if selected_containers else None

        self._spaces_raw: list[dict[str, Any]] | None = None
        self._pages_by_space: dict[str, list[dict[str, Any]]] = {}
        self._page_by_native_id: dict[str, dict[str, Any]] = {}
        self._attachments_by_page: dict[str, list[dict[str, Any]]] = {}
        self._comments_by_page: dict[str, list[dict[str, Any]]] = {}
        self._comment_by_native_id: dict[str, dict[str, Any]] = {}
        self._blog_posts_by_space: dict[str, list[dict[str, Any]]] = {}
        self._blog_post_by_native_id: dict[str, dict[str, Any]] = {}
        # account_id -> display name (None if the lookup failed/wasn't
        # found) — one cached call per unique person, same pattern as
        # _fetch_labels below.
        self._person_display_name_cache: dict[str, str | None] = {}
        self._restrictions_by_page: dict[str, dict[str, Any]] = {}

    # -- low-level HTTP -----------------------------------------------

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        async def do_call() -> httpx.Response:
            response = await self.client.request(method, path, **kwargs)
            self.raise_for_status_category(response)
            return response

        response = await self.call_with_retry(do_call)
        result: dict[str, Any] = response.json()
        return result

    async def _paginated(self, path: str, **params: Any) -> list[dict[str, Any]]:
        """Confluence v2's pagination is cursor-based via `_links.next`
        (a relative URL that already carries the next cursor and every
        original query param) rather than a page number — follow it
        until absent."""
        results: list[dict[str, Any]] = []
        next_path: str | None = path
        next_params: dict[str, Any] | None = {"limit": _PAGE_LIMIT, **params}
        while next_path:
            data = await self._request("GET", next_path, params=next_params)
            results.extend(data.get("results", []))
            next_path = (data.get("_links") or {}).get("next")
            next_params = None  # the next link already encodes params
        return results

    # -- discovery / hierarchy ------------------------------------------

    def _apply_space_filter(self, spaces: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if self._selected_containers is None:
            return spaces
        selected = self._selected_containers
        return [s for s in spaces if str(s["id"]) in selected or s.get("key") in selected]

    async def discover_containers(self) -> list[SourceContainer]:
        # description-format=plain: without it, Confluence's v2 /spaces
        # response always returns description=None regardless of whether
        # the space actually has one set (confirmed live) — same
        # opt-in-format convention as body-format on the pages endpoint.
        all_spaces = await self._paginated("/spaces", **{"description-format": "plain"})
        self._spaces_raw = self._apply_space_filter(all_spaces)
        return [mapper.map_space(s) for s in self._spaces_raw]

    async def _space_ids(self) -> set[str]:
        if self._spaces_raw is None:
            await self.discover_containers()
        return {str(s["id"]) for s in (self._spaces_raw or [])}

    async def _ensure_pages_for_space(self, space_id: str) -> list[dict[str, Any]]:
        if space_id not in self._pages_by_space:
            raw_pages = await self._paginated(
                f"/spaces/{space_id}/pages", **{"body-format": "storage"}
            )
            pages = [self._flatten_page(p, space_id) for p in raw_pages]
            for p in pages:
                p["labels"] = await self._fetch_labels(str(p["id"]))
                p.update(await self._fetch_restrictions(str(p["id"])))
            self._pages_by_space[space_id] = pages
            for p in pages:
                self._page_by_native_id[str(p["id"])] = p
        return self._pages_by_space[space_id]

    async def _fetch_labels(self, page_id: str) -> list[str]:
        """Confluence's own page labels (`/pages/{id}/labels`) — real
        vendor metadata a human already attached, not inferred. The v2
        REST API doesn't support inlining these on the pages-list
        response (a v1-only `expand` feature), so this is a separate call
        per page, same cost tier as the existing per-page attachments/
        comments calls."""
        raw_labels = await self._paginated(f"/pages/{page_id}/labels")
        return [label.get("name", "") for label in raw_labels if label.get("name")]

    async def _fetch_display_name(self, account_id: str) -> str | None:
        """A PERSON node named by a raw account-id-shaped string is nearly
        useless in the UI — one cached lookup per unique account_id (same
        per-item auxiliary-fetch pattern as _fetch_labels above). The v2
        API has no user-lookup endpoint at all; this is v1's
        `/rest/api/user`, requested as an absolute path
        ("/wiki/rest/api/user...") rather than relative to this client's
        own v2 base_url ("<site>/wiki/api/v2") — a leading-slash request
        path replaces base_url's whole path component (RFC 3986), so a
        bare "/rest/api/user" would resolve to "<site>/rest/api/user" and
        404. Best-effort: some tokens can lack user-lookup scope, so a
        failure here degrades to the account id as the display name
        rather than failing the whole sync."""
        if account_id in self._person_display_name_cache:
            return self._person_display_name_cache[account_id]
        name: str | None = None
        try:
            data = await self._request(
                "GET", "/wiki/rest/api/user", params={"accountId": account_id}
            )
            name = data.get("displayName")
        except (AuthError, NotFound, Permanent) as exc:
            logger.warning(
                "confluence.display_name_unavailable", account_id=account_id, error=str(exc)
            )
        self._person_display_name_cache[account_id] = name
        return name

    async def _fetch_restrictions(self, page_id: str) -> dict[str, Any]:
        """`/pages/{id}/restrictions` — real permission-boundary data the
        graph would otherwise have no record of at all (docs/CONNECTORS.md
        — "what to also extract"). Data capture only: this does not add
        any actual enforcement (authorization/ doesn't exist yet, same
        standing gap as everywhere else in this codebase) — it just means
        the fact "this page is restricted, to these accounts" is no
        longer silently lost. Built from Atlassian's documented v2 shape;
        not live-verified against a real restricted page the way the rest
        of this connector's endpoints were (same honesty precedent as
        azure_devops/live.py's test-hierarchy fetch) — defensively parsed
        so an unexpected shape degrades to "no restriction data" rather
        than raising."""
        if page_id in self._restrictions_by_page:
            return self._restrictions_by_page[page_id]
        result = {"restricted": False, "restriction_subjects": []}
        try:
            raw_restrictions = await self._paginated(f"/pages/{page_id}/restrictions")
        except (AuthError, NotFound, Permanent) as exc:
            logger.warning(
                "confluence.restrictions_unavailable", page_id=page_id, error=str(exc)
            )
            self._restrictions_by_page[page_id] = result
            return result
        subjects: set[str] = set()
        for entry in raw_restrictions:
            restrictions = entry.get("restrictions") or {}
            for kind in ("user", "group"):
                for subject in (restrictions.get(kind) or {}).get("results", []) or []:
                    subject_id = subject.get("accountId") or subject.get("id")
                    if subject_id:
                        subjects.add(str(subject_id))
        result = {"restricted": bool(raw_restrictions), "restriction_subjects": sorted(subjects)}
        self._restrictions_by_page[page_id] = result
        return result

    async def _ensure_blog_posts_for_space(self, space_id: str) -> list[dict[str, Any]]:
        if space_id not in self._blog_posts_by_space:
            raw_posts = await self._paginated(
                f"/spaces/{space_id}/blogposts", **{"body-format": "storage"}
            )
            posts = [self._flatten_page(p, space_id) for p in raw_posts]
            for p in posts:
                p["labels"] = await self._fetch_labels(str(p["id"]))
            self._blog_posts_by_space[space_id] = posts
            for p in posts:
                self._blog_post_by_native_id[f"BLOG-{p['id']}"] = p
        return self._blog_posts_by_space[space_id]

    @staticmethod
    def _flatten_page(raw: dict[str, Any], space_id: str) -> dict[str, Any]:
        body = ((raw.get("body") or {}).get("storage") or {}).get("value", "")
        return {
            "id": raw["id"],
            "spaceId": raw.get("spaceId", space_id),
            "parentId": raw.get("parentId"),
            "title": raw.get("title", ""),
            "status": raw.get("status", "current"),
            "version": (raw.get("version") or {}).get("number", ""),
            "body": body,
            "url": raw.get("_links", {}).get("webui", ""),
            "authorId": raw.get("authorId", ""),
            # Confluence has no "last modified" field — the current
            # version's own createdAt *is* the last-modified time.
            "updatedAt": (raw.get("version") or {}).get("createdAt", ""),
            # The page's own creation, distinct from the current version's.
            "createdAt": raw.get("createdAt", ""),
        }

    async def _ensure_attachments_for_page(self, page_id: str) -> list[dict[str, Any]]:
        if page_id not in self._attachments_by_page:
            raw_attachments = await self._paginated(f"/pages/{page_id}/attachments")
            attachments = [
                {
                    "id": a["id"],
                    "pageId": page_id,
                    "title": a.get("title", ""),
                    "mediaType": a.get("mediaType", ""),
                    "fileSize": a.get("fileSize", 0),
                    "url": a.get("_links", {}).get("webui", ""),
                }
                for a in raw_attachments
            ]
            self._attachments_by_page[page_id] = attachments
        return self._attachments_by_page[page_id]

    async def _ensure_comments_for_page(self, page_id: str) -> list[dict[str, Any]]:
        if page_id not in self._comments_by_page:
            raw_comments = await self._paginated(
                f"/pages/{page_id}/footer-comments", **{"body-format": "storage"}
            )
            comments = []
            for c in raw_comments:
                body = ((c.get("body") or {}).get("storage") or {}).get("value", "")
                comment = {
                    "id": c["id"],
                    "pageId": page_id,
                    "body": body,
                    "author": (c.get("version") or {}).get("authorId", ""),
                    "url": c.get("_links", {}).get("webui", ""),
                }
                comments.append(comment)
                self._comment_by_native_id[f"COMMENT-{comment['id']}"] = comment
            self._comments_by_page[page_id] = comments
        return self._comments_by_page[page_id]

    async def _person_items(
        self, pages: list[dict[str, Any]], *, parent_id: str, key: str
    ) -> list[SourceObject]:
        """PERSON items for every distinct account id at `key` (authorId
        on a page, author on a comment) across `pages`. Deduped and
        returned as a plain list — callers prepend these ahead of the
        items that reference them; see list_children's own docstring note
        for why order matters here."""
        items: list[SourceObject] = []
        seen: set[str] = set()
        for p in pages:
            account_id = p.get(key)
            if account_id and account_id not in seen:
                seen.add(account_id)
                display_name = await self._fetch_display_name(account_id)
                items.append(
                    mapper.map_person(account_id, display_name, parent_native_id=parent_id)
                )
        return items

    async def list_children(self, parent_id: str, cursor: str | None = None) -> Page[SourceObject]:
        # Ordering matters, not just presence: synchronization/
        # orchestrator.py upserts each returned item in order and calls
        # get_links() on it *immediately* — before ever calling
        # list_children on that item itself. A page's AUTHORED_BY/
        # HAS_LABEL edges (emitted from the page's own get_links()) can
        # only resolve if the PERSON/LABEL node they target was already
        # upserted earlier in this *same* items list — so those
        # dependency nodes are emitted as the page's siblings, before it,
        # here, rather than as the page's own children one BFS level
        # later (which could never resolve on a fresh sync — a real bug
        # this ordering guards against).
        space_ids = await self._space_ids()

        if parent_id in space_ids:
            items: list[SourceObject] = []
            pages: list[dict[str, Any]] = []
            if "pages" in self._entity_types:
                pages = await self._ensure_pages_for_space(parent_id)
            top_pages = [
                p for p in pages if not p.get("parentId") and str(p["spaceId"]) == parent_id
            ]
            if "people" in self._entity_types and pages:
                # Every page in the space, not just top-level ones —
                # nested pages' authors are covered here too, so the
                # page-id branch below never needs its own author lookup.
                items += await self._person_items(pages, parent_id=parent_id, key="authorId")
            seen_labels: set[str] = set()
            for p in top_pages:
                for name in p.get("labels", []) or []:
                    if name not in seen_labels:
                        seen_labels.add(name)
                        items.append(mapper.map_label(name, parent_native_id=parent_id))
            items += [mapper.map_page(p) for p in top_pages]
            if "blogposts" in self._entity_types:
                # Blog posts are leaves this pass — no comment/attachment
                # drill-down (those need their own /blogposts/{id}/...
                # endpoints, not implemented here), same scope limit as
                # this connector's other "known simplifications".
                posts = await self._ensure_blog_posts_for_space(parent_id)
                if "people" in self._entity_types:
                    items += await self._person_items(posts, parent_id=parent_id, key="authorId")
                items += [mapper.map_blog_post(p) for p in posts]
            return Page(items=items, next_cursor=None)

        if parent_id in self._page_by_native_id:
            items = []
            page_data = self._page_by_native_id[parent_id]
            child_pages: list[dict[str, Any]] = []
            if "pages" in self._entity_types:
                # A page's child pages live in the same per-space cache
                # already fetched — filter rather than re-request.
                space_id = str(page_data["spaceId"])
                pages = await self._ensure_pages_for_space(space_id)
                child_pages = [p for p in pages if str(p.get("parentId") or "") == parent_id]
                if "people" in self._entity_types:
                    items += await self._person_items(
                        child_pages, parent_id=parent_id, key="authorId"
                    )
                seen_labels = set()
                for p in child_pages:
                    for name in p.get("labels", []) or []:
                        if name not in seen_labels:
                            seen_labels.add(name)
                            items.append(mapper.map_label(name, parent_native_id=parent_id))
                items += [mapper.map_page(p) for p in child_pages]
            if "attachments" in self._entity_types:
                attachments = await self._ensure_attachments_for_page(parent_id)
                items += [mapper.map_attachment(a) for a in attachments]
            if "comments" in self._entity_types:
                comments = await self._ensure_comments_for_page(parent_id)
                if "people" in self._entity_types:
                    # Comment authors aren't known until comments are
                    # fetched (lazily, here) — unlike page authors above,
                    # which are known as soon as the space's pages are.
                    items += await self._person_items(comments, parent_id=parent_id, key="author")
                items += [mapper.map_comment(c) for c in comments]
            # This page's own labels are not re-listed as its children
            # here — they were already emitted as its *siblings* by
            # whichever call first listed this page (the space branch, or
            # this same branch's child_pages handling above), which is
            # also where they live in the tree (one label can apply to
            # many pages, so it can't structurally be "owned" by any one
            # of them). Re-emitting them here would just be a redundant
            # upsert with no new information.
            return Page(items=items, next_cursor=None)

        return Page(items=[], next_cursor=None)

    # -- single-object lookups -------------------------------------------

    async def get_object(self, native_id: str) -> SourceObject:
        if native_id in self._page_by_native_id:
            return mapper.map_page(self._page_by_native_id[native_id])
        if native_id in self._comment_by_native_id:
            return mapper.map_comment(self._comment_by_native_id[native_id])
        if native_id in self._blog_post_by_native_id:
            return mapper.map_blog_post(self._blog_post_by_native_id[native_id])
        for attachments in self._attachments_by_page.values():
            for a in attachments:
                if f"ATT-{a['id']}" == native_id:
                    return mapper.map_attachment(a)
        raise NotFound(
            f"no Confluence object with native_id={native_id!r}", source_system=self.source_system
        )

    async def get_content(self, native_id: str, version: str | None = None) -> SourceContent:
        if native_id in self._page_by_native_id:
            return mapper.map_page_content(native_id, self._page_by_native_id[native_id])
        if native_id in self._comment_by_native_id:
            return mapper.map_comment_content(native_id, self._comment_by_native_id[native_id])
        if native_id in self._blog_post_by_native_id:
            return mapper.map_page_content(native_id, self._blog_post_by_native_id[native_id])
        raise NotFound(f"no content for native_id={native_id!r}", source_system=self.source_system)

    # -- change feed / links / acl ----------------------------------------

    async def get_changes(self, cursor: str | None = None) -> ChangePage:
        """No incremental delta feed implemented yet — see module
        docstring's "Known simplifications"."""
        return ChangePage(items=[], next_cursor=None, has_more=False)

    async def get_links(self, native_id: str) -> list[SourceLink]:
        if native_id in self._page_by_native_id or native_id in self._blog_post_by_native_id:
            page_data = self._page_by_native_id.get(native_id) or self._blog_post_by_native_id[
                native_id
            ]
            links = mapper.extract_structured_links(native_id, page_data["body"])
            links += mapper.map_page_relationship_links(
                native_id,
                space_native_id=str(page_data["spaceId"]),
                author_account_id=page_data.get("authorId") or None,
                label_names=page_data.get("labels") or [],
            )
            return links
        if native_id in self._comment_by_native_id:
            comment_data = self._comment_by_native_id[native_id]
            # Previously defaulted to location="page_body" (0.85) same as
            # a page — a comment is a passing mention, not a declared
            # spec, and belongs at the "comment" tier (0.70).
            links = mapper.extract_structured_links(
                native_id, comment_data["body"], location="comment"
            )
            links += mapper.map_comment_relationship_links(
                native_id, author_account_id=comment_data.get("author") or None
            )
            return links
        return []

    async def get_acl_reference(self, native_id: str) -> ACLReference:
        space_key = None
        acl: dict[str, Any] = {}
        if native_id in self._page_by_native_id and self._spaces_raw:
            page_data = self._page_by_native_id[native_id]
            space_id = str(page_data["spaceId"])
            space_key = next(
                (s.get("key") for s in self._spaces_raw if str(s["id"]) == space_id), None
            )
            if page_data.get("restricted"):
                acl["restriction_subjects"] = page_data.get("restriction_subjects", [])
        if space_key:
            acl["space"] = space_key
        return ACLReference(native_id=native_id, acl_ref=acl)
