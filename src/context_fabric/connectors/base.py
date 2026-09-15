"""SourceConnector protocol and shared connector infrastructure.

Defines the seven async methods every connector implements
(docs/CONNECTORS.md), plus the cross-cutting base classes so no connector
reimplements retry/backoff/correlation logic: `FixtureConnectorBase`
(fixture mode) and `LiveConnectorBase` (live mode, Phase 19).

Depends only on domain/. First concrete connector lands in Phase 4.
"""

from __future__ import annotations

import json
import uuid
from abc import ABC
from collections.abc import Awaitable, Callable
from functools import wraps
from pathlib import Path
from typing import (
    Any,
    ClassVar,
    Literal,
    Protocol,
    TypeVar,
    runtime_checkable,
)

import httpx
import structlog
import tenacity
from pydantic import BaseModel, ValidationError

from context_fabric.domain.connector_types import (
    ACLReference,
    ChangePage,
    Page,
    SourceContainer,
    SourceContent,
    SourceLink,
    SourceObject,
)
from context_fabric.domain.errors import (
    AuthError,
    NotFound,
    Permanent,
    RateLimited,
    SchemaDrift,
    Transient,
)

FIXTURES_ROOT = Path(__file__).resolve().parents[3] / "fixtures"

M = TypeVar("M", bound=BaseModel)
R = TypeVar("R")


# ---------------------------------------------------------------------------
# The protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class SourceConnector(Protocol):
    """The contract every connector implements, in both fixture and live
    mode (docs/CONNECTORS.md). Seven async methods. No method may return
    a vendor SDK object or a raw dict shaped like the vendor's JSON
    (AGENTS.md §5) — every return type here is a domain/ type.
    """

    source_system: str
    mode: Literal["fixture", "live"]

    async def discover_containers(self) -> list[SourceContainer]:
        """Top-level containers this connector instance can see — e.g.
        ADO projects, GitHub orgs/repos."""
        ...

    async def list_children(self, parent_id: str, cursor: str | None = None) -> Page[SourceObject]:
        """Paginated children of a container or object, in native
        hierarchy order (docs/CONNECTORS.md "Native hierarchies")."""
        ...

    async def get_object(self, native_id: str) -> SourceObject: ...

    async def get_content(self, native_id: str, version: str | None = None) -> SourceContent:
        """Full body, fetched on demand only (ADR-003) — never called by
        sync itself, only by expand_evidence/refresh_evidence."""
        ...

    async def get_changes(self, cursor: str | None = None) -> ChangePage:
        """Delta feed since cursor, including deletions/tombstones."""
        ...

    async def get_links(self, native_id: str) -> list[SourceLink]:
        """Explicit and mentioned links out of this object, for
        relationship extraction (synchronization/, not retrieval/)."""
        ...

    async def get_acl_reference(self, native_id: str) -> ACLReference:
        """Opaque pointer, resolved later by authorization/. A connector
        never decides who can read something — it only reports the
        source's own access-control identity for that object."""
        ...


# ---------------------------------------------------------------------------
# Correlation IDs
# ---------------------------------------------------------------------------


class correlate:
    """Binds `correlation_id` into structlog's contextvars for the
    duration of a call, so every log line emitted underneath carries it
    automatically (docs/CONNECTORS.md "Correlation IDs").

    Usable as a context manager (`with correlate(run_id): ...`) or as a
    decorator on an async method (`@correlate()`). If a correlation_id is
    already bound in the current context (e.g. an enclosing sync-run
    orchestrator already set one, Phase 6), it is inherited rather than
    overwritten — `correlate()` decorating an individual connector method
    is a safety net ensuring one always exists, not a per-call reset.
    """

    def __init__(self, correlation_id: str | None = None) -> None:
        self._explicit_id = correlation_id
        self._tokens: dict[str, Any] | None = None

    def __enter__(self) -> str:
        existing = structlog.contextvars.get_contextvars().get("correlation_id")
        if existing and self._explicit_id is None:
            self._tokens = None
            return str(existing)
        cid = self._explicit_id or str(uuid.uuid4())
        self._tokens = dict(structlog.contextvars.bind_contextvars(correlation_id=cid))
        return cid

    def __exit__(self, *exc_info: object) -> None:
        if self._tokens is not None:
            structlog.contextvars.reset_contextvars(**self._tokens)

    def __call__(self, func: Callable[..., Awaitable[R]]) -> Callable[..., Awaitable[R]]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> R:
            with correlate(self._explicit_id):
                return await func(*args, **kwargs)

        return wrapper


# ---------------------------------------------------------------------------
# Fixture mode
# ---------------------------------------------------------------------------


class FixtureConnectorBase(ABC):
    """Base for every fixture-mode connector. Loads deterministic JSON
    from fixtures/<source_system>/ — no network, no credentials. Does not
    itself implement SourceConnector's methods (their shape is
    source-specific, Phase 4+); provides the helpers those
    implementations use.
    """

    source_system: ClassVar[str]
    mode: Literal["fixture"] = "fixture"

    def __init__(self, fixtures_dir: Path | None = None) -> None:
        self.fixtures_dir = fixtures_dir or (FIXTURES_ROOT / self.source_system)

    def load_json(self, relative_path: str) -> Any:
        """Read + parse one fixture JSON file. Raises NotFound if the
        file doesn't exist, SchemaDrift if it isn't valid JSON."""
        path = self.fixtures_dir / relative_path
        if not path.exists():
            raise NotFound(
                f"fixture file not found: {relative_path}",
                source_system=self.source_system,
            )
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise SchemaDrift(
                f"fixture file {relative_path} is not valid JSON: {exc}",
                source_system=self.source_system,
            ) from exc

    def parse_many(self, model_cls: type[M], items: list[Any]) -> list[M]:
        """Validate a list of raw dicts into `model_cls` (a domain/
        type). Raises SchemaDrift, naming the offending item, on the
        first mismatch — never silently drops or coerces a bad record."""
        results: list[M] = []
        for i, raw in enumerate(items):
            try:
                results.append(model_cls.model_validate(raw))
            except ValidationError as exc:
                raise SchemaDrift(
                    f"fixture item {i} does not match {model_cls.__name__}: {exc}",
                    source_system=self.source_system,
                ) from exc
        return results

    def find_by_native_id(self, items: list[M], native_id: str) -> M:
        """Look up one item by its native_id field. Raises NotFound (not
        IndexError/StopIteration) if absent."""
        for item in items:
            if getattr(item, "native_id", None) == native_id:
                return item
        raise NotFound(
            f"no object with native_id={native_id!r} in fixture data",
            source_system=self.source_system,
        )


# ---------------------------------------------------------------------------
# Live mode
# ---------------------------------------------------------------------------

DEFAULT_TIMEOUT = httpx.Timeout(10.0, connect=5.0)


def _is_retryable(exc: BaseException) -> bool:
    return isinstance(exc, Transient | RateLimited)


class LiveConnectorBase(ABC):
    """Base for every live-mode connector (Phase 19). An httpx client
    pre-wired with a timeout, plus a reusable retry wrapper: bounded
    exponential backoff with jitter, retried only for Transient/
    RateLimited — never AuthError/NotFound/Permanent/SchemaDrift
    (docs/CONNECTORS.md "Retry").
    """

    source_system: ClassVar[str]
    mode: Literal["live"] = "live"

    def __init__(
        self,
        base_url: str,
        *,
        timeout: httpx.Timeout = DEFAULT_TIMEOUT,
        headers: dict[str, str] | None = None,
        max_attempts: int = 5,
        backoff_multiplier: float = 0.5,
        backoff_max: float = 30.0,
    ) -> None:
        self.client = httpx.AsyncClient(base_url=base_url, timeout=timeout, headers=headers or {})
        self._max_attempts = max_attempts
        self._backoff_multiplier = backoff_multiplier
        self._backoff_max = backoff_max
        # Every optional entity type this connector instance silently
        # degraded on this run (caught AuthError/NotFound/Permanent and
        # returned an empty result instead of failing the whole sync —
        # docs/CONNECTORS.md "Entity type selection"). synchronization/
        # orchestrator.py's tombstone sweep checks this before treating
        # "not seen this pass" as "deleted upstream" — a degraded fetch
        # (e.g. a PAT missing one scope) must never be read as "every
        # previously-synced item of that type is now gone" (found via a
        # real case: ADO builds returning [] on a 403 would otherwise
        # tombstone every already-synced BUILD node).
        self._degraded_entity_types: set[str] = set()

    def _mark_degraded(self, entity_type: str, reason: str) -> None:
        self._degraded_entity_types.add(entity_type)
        structlog.get_logger().warning(
            "connector.entity_type_degraded",
            source_system=self.source_system,
            entity_type=entity_type,
            reason=reason,
        )

    @property
    def degraded_entity_types(self) -> set[str]:
        return self._degraded_entity_types

    async def aclose(self) -> None:
        await self.client.aclose()

    def _retryer(self) -> tenacity.AsyncRetrying:
        exponential_jitter = tenacity.wait_random_exponential(
            multiplier=self._backoff_multiplier, max=self._backoff_max
        )

        def wait(retry_state: tenacity.RetryCallState) -> float:
            outcome = retry_state.outcome
            exc = outcome.exception() if outcome is not None else None
            if isinstance(exc, RateLimited) and exc.retry_after_seconds is not None:
                return exc.retry_after_seconds
            return float(exponential_jitter(retry_state))

        return tenacity.AsyncRetrying(
            retry=tenacity.retry_if_exception(_is_retryable),
            wait=wait,
            stop=tenacity.stop_after_attempt(self._max_attempts),
            reraise=True,
        )

    async def call_with_retry(self, func: Callable[[], Awaitable[R]]) -> R:
        """Runs `func` under the retry policy above. AuthError, NotFound,
        Permanent, and SchemaDrift propagate on the first attempt."""
        async for attempt in self._retryer():
            with attempt:
                return await func()
        raise AssertionError("unreachable: tenacity always returns or raises")

    def raise_for_status_category(self, response: httpx.Response) -> None:
        """Maps an HTTP response's status code to one of the explicit
        error categories (docs/CONVENTIONS.md "Error categories"). Called
        by live.py implementations after every request."""
        status = response.status_code
        url = response.request.url
        if status in (401, 403):
            raise AuthError(f"{status} from {url}", source_system=self.source_system)
        if status == 404:
            raise NotFound(f"{status} from {url}", source_system=self.source_system)
        if status == 429:
            retry_after = response.headers.get("Retry-After")
            raise RateLimited(
                f"{status} from {url}",
                source_system=self.source_system,
                retry_after_seconds=float(retry_after) if retry_after else None,
            )
        if status >= 500:
            raise Transient(f"{status} from {url}", source_system=self.source_system)
        if status >= 400:
            raise Permanent(f"{status} from {url}", source_system=self.source_system)
