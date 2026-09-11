"""Explicit connector/sync error categories.

docs/CONVENTIONS.md "Error categories": callers branch on category
(`except RateLimited:`), never on message text or status code directly
outside the connector that raised it. `category` is redundant with the
exception's own type but is included so an error can be logged/serialized
generically (e.g. into sync_run.error_category, docs/persistence.md)
without a type-name-to-string mapping living somewhere else.
"""

from __future__ import annotations

from context_fabric.domain.enums import ErrorCategory


class ConnectorError(Exception):
    """Base class for every error a SourceConnector may raise. Never raised
    directly — always one of the categorized subclasses below."""

    category: ErrorCategory

    def __init__(self, message: str, *, source_system: str | None = None) -> None:
        super().__init__(message)
        self.source_system = source_system


class AuthError(ConnectorError):
    """Bad/expired credential, or insufficient vendor permission. Never
    retried."""

    category = ErrorCategory.AUTH


class RateLimited(ConnectorError):
    """Vendor rate limit hit. Retryable after backoff."""

    category = ErrorCategory.RATE_LIMITED

    def __init__(
        self,
        message: str,
        *,
        source_system: str | None = None,
        retry_after_seconds: float | None = None,
    ) -> None:
        super().__init__(message, source_system=source_system)
        self.retry_after_seconds = retry_after_seconds


class NotFound(ConnectorError):
    """Object doesn't exist. May mean deleted; sync treats this distinctly
    from a get_changes-reported tombstone (docs/CONNECTORS.md)."""

    category = ErrorCategory.NOT_FOUND


class Transient(ConnectorError):
    """Network/timeout/5xx. Retryable."""

    category = ErrorCategory.TRANSIENT


class Permanent(ConnectorError):
    """4xx other than auth/not-found/rate-limit. Not retryable."""

    category = ErrorCategory.PERMANENT


class SchemaDrift(ConnectorError):
    """Vendor payload shape didn't match what mapper.py expects. Never
    silently coerced — always raised and logged."""

    category = ErrorCategory.SCHEMA_DRIFT
