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
from context_fabric.domain.errors import NotFound

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
            "updatedAt": (raw.get("version") or {}).get("createdAt", ""),
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

    async def list_children(self, parent_id: str, cursor: str | None = None) -> Page[SourceObject]:
        space_ids = await self._space_ids()

        if parent_id in space_ids:
            if "pages" not in self._entity_types:
                return Page(items=[], next_cursor=None)
            pages = await self._ensure_pages_for_space(parent_id)
            items = [
                mapper.map_page(p)
                for p in pages
                if not p.get("parentId") and str(p["spaceId"]) == parent_id
            ]
            return Page(items=items, next_cursor=None)

        if parent_id in self._page_by_native_id:
            items = []
            if "pages" in self._entity_types:
                # A page's child pages live in the same per-space cache
                # already fetched — filter rather than re-request.
                space_id = str(self._page_by_native_id[parent_id]["spaceId"])
                pages = await self._ensure_pages_for_space(space_id)
                items += [
                    mapper.map_page(p) for p in pages if str(p.get("parentId") or "") == parent_id
                ]
            if "attachments" in self._entity_types:
                attachments = await self._ensure_attachments_for_page(parent_id)
                items += [mapper.map_attachment(a) for a in attachments]
            if "comments" in self._entity_types:
                comments = await self._ensure_comments_for_page(parent_id)
                items += [mapper.map_comment(c) for c in comments]
            return Page(items=items, next_cursor=None)

        return Page(items=[], next_cursor=None)

    # -- single-object lookups -------------------------------------------

    async def get_object(self, native_id: str) -> SourceObject:
        if native_id in self._page_by_native_id:
            return mapper.map_page(self._page_by_native_id[native_id])
        if native_id in self._comment_by_native_id:
            return mapper.map_comment(self._comment_by_native_id[native_id])
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
        raise NotFound(
            f"no content for native_id={native_id!r}", source_system=self.source_system
        )

    # -- change feed / links / acl ----------------------------------------

    async def get_changes(self, cursor: str | None = None) -> ChangePage:
        """No incremental delta feed implemented yet — see module
        docstring's "Known simplifications"."""
        return ChangePage(items=[], next_cursor=None, has_more=False)

    async def get_links(self, native_id: str) -> list[SourceLink]:
        if native_id in self._page_by_native_id:
            body = self._page_by_native_id[native_id]["body"]
            return mapper.map_links_from_text(native_id, body)
        if native_id in self._comment_by_native_id:
            body = self._comment_by_native_id[native_id]["body"]
            return mapper.map_links_from_text(native_id, body)
        return []

    async def get_acl_reference(self, native_id: str) -> ACLReference:
        space_key = None
        if native_id in self._page_by_native_id and self._spaces_raw:
            space_id = str(self._page_by_native_id[native_id]["spaceId"])
            space_key = next(
                (s.get("key") for s in self._spaces_raw if str(s["id"]) == space_id), None
            )
        return ACLReference(native_id=native_id, acl_ref={"space": space_key} if space_key else {})
