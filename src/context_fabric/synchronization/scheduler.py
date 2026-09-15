"""Periodic background sync.

Fixes a real failure observed this session: sync only ever ran when a human
remembered to POST the trigger endpoint, so a connector that started failing
(Confluence, on an expired token) stayed silently broken for the rest of the
session — `sync_state` recorded the truth the whole time, but nothing ever
looked at it, because nothing ever ran again to notice. This loop calls the
exact same `sync_source` the manual trigger endpoint uses, on an interval, so
a stopped-working connector shows up as `status=FAILED` within one cycle
instead of indefinitely.

Deliberately NOT incremental. Every tick is a full walk — today's
`sync_source`, unchanged. Incrementality (SyncState.cursor, a per-connector
delta query) is a fetch-side optimization layered on top of this loop, not a
property of the loop itself; this module's only job is "make sync happen
regularly, and never let one connection's failure stop the others."
"""

from __future__ import annotations

import asyncio

import structlog

from context_fabric.connectors.credentials import decrypt_credential
from context_fabric.domain.errors import ConnectorError
from context_fabric.persistence.repositories.connector_connection import (
    ConnectorConnectionRepository,
)
from context_fabric.persistence.session import session_scope
from context_fabric.settings import Settings
from context_fabric.synchronization import sync_source

logger = structlog.get_logger()


async def sync_all_connections() -> None:
    """One pass over every configured connection.

    Each connection gets its own session and its own try/except — a
    single connection's failure (an expired token, a rate limit) is
    logged and skipped, never allowed to abort the pass for the rest.
    Letting one broken connector stop every *other* connector from
    updating would just be a different, worse version of the exact
    problem this loop exists to fix.
    """
    # Imported here, not at module scope: connectors.py's `_build_connector`
    # is the one place that already knows which live connector class needs
    # which constructor kwargs (org_url+pat vs org+token vs
    # site_url+email+api_token, ...) — reusing it avoids re-deriving that
    # mapping a second time. The import lives inside the function so the
    # synchronization package doesn't gain a module-level dependency on the
    # api package; a future cleanup could hoist _build_connector into
    # connectors/registry.py so both sides import it from something neither
    # of them owns.
    from context_fabric.api.routes.connectors import _build_connector

    settings = Settings()
    async with session_scope() as session:
        connections = await ConnectorConnectionRepository(session).list_all()

    for summary in connections:
        connector = None
        async with session_scope() as session:
            conn_repo = ConnectorConnectionRepository(session)
            credential = None
            if summary.mode == "live":
                ciphertext = await conn_repo.get_credential_ciphertext(summary.id)
                if ciphertext is None or not settings.CF_SECRET_KEY:
                    logger.warning(
                        "scheduler.sync_skipped",
                        source_system=summary.source_system,
                        instance_id=summary.instance_id,
                        reason="no_usable_credential",
                    )
                    continue
                credential = decrypt_credential(ciphertext, settings.CF_SECRET_KEY)

            try:
                connector = _build_connector(
                    summary.source_system, summary.mode, summary.config, credential
                )
                await sync_source(session, connector, source_instance_id=summary.instance_id)
                logger.info(
                    "scheduler.sync_completed",
                    source_system=summary.source_system,
                    instance_id=summary.instance_id,
                )
            except ConnectorError as exc:
                # sync_source already recorded the failed SyncRun/SyncState
                # before re-raising — nothing further to persist here, this
                # is purely so the scheduler's own log carries the signal
                # too, and the next connection in the loop still runs.
                logger.warning(
                    "scheduler.sync_failed",
                    source_system=summary.source_system,
                    instance_id=summary.instance_id,
                    error=str(exc),
                )
            except Exception:
                # An error sync_source itself couldn't categorize (a bug,
                # not a vendor condition) — logged with a stack trace
                # rather than re-raised, since a scheduler that dies on the
                # first unexpected exception defeats its own purpose.
                logger.exception(
                    "scheduler.sync_unexpected_error",
                    source_system=summary.source_system,
                    instance_id=summary.instance_id,
                )
            finally:
                if connector is not None and hasattr(connector, "aclose"):
                    await connector.aclose()  # type: ignore[attr-defined]


async def run_forever(interval_seconds: int) -> None:
    """The loop itself. Run as a background task from the app's lifespan
    and cancelled on shutdown — see main.py."""
    logger.info("scheduler.started", interval_seconds=interval_seconds)
    while True:
        try:
            await sync_all_connections()
        except Exception:
            # A failure in the pass-level plumbing (e.g. the database is
            # briefly unreachable when listing connections) must not kill
            # the scheduler outright — it gets another attempt next
            # interval, the same tolerance given to any single connection.
            logger.exception("scheduler.pass_failed")
        await asyncio.sleep(interval_seconds)
