"""Connector connection config + test-connection + sync trigger/status
(docs/API.md "Connectors"). credential is write-only — accepted on
create, never returned by any read here (docs/SECURITY.md).
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from context_fabric.api.deps import get_session
from context_fabric.connectors import get_fixture_connector_class
from context_fabric.connectors.azure_devops.live import AzureDevOpsLiveConnector
from context_fabric.connectors.base import SourceConnector
from context_fabric.connectors.confluence.live import ConfluenceLiveConnector
from context_fabric.connectors.credentials import decrypt_credential, encrypt_credential
from context_fabric.connectors.github.live import GitHubLiveConnector
from context_fabric.connectors.jira.live import JiraLiveConnector
from context_fabric.connectors.teams.live import TeamsLiveConnector
from context_fabric.domain.errors import ConnectorError
from context_fabric.enrichment.confluence_abstracts import enrich_confluence_pages
from context_fabric.enrichment.node_embeddings import enrich_node_embeddings
from context_fabric.enrichment.ollama_client import OllamaClient
from context_fabric.persistence.repositories.connector_connection import (
    ConnectorConnectionRepository,
    ConnectorConnectionSummary,
)
from context_fabric.persistence.repositories.node import NodeRepository
from context_fabric.persistence.repositories.sync_run import SyncRunRepository
from context_fabric.persistence.repositories.sync_state import SyncStateRepository
from context_fabric.settings import Settings
from context_fabric.synchronization import sync_source
from context_fabric.synchronization.orchestrator import SyncMode

router = APIRouter(prefix="/api/connectors", tags=["connectors"])

# What each source needs, so the UI can render the right fields and this
# module can validate them before ever touching the network. Config keys
# match connections.config's stored shape.
LIVE_CONFIG_FIELDS: dict[str, list[str]] = {
    "azure_devops": ["org_url"],
    "github": ["org"],
    "confluence": ["site_url", "email"],
    "jira": ["site_url", "email"],
    "teams": ["tenant_id", "team_id", "client_id"],
}

# The "what to pull" checkboxes the UI renders per source system
# (docs/CONNECTORS.md "Entity type selection") — the single source of
# truth is each live connector's own ENTITY_TYPES class attribute; this
# just collects them so the UI never has to hardcode a copy that could
# drift out of sync with what the connector actually implements.
ENTITY_TYPES_BY_SOURCE: dict[str, dict[str, str]] = {
    "azure_devops": AzureDevOpsLiveConnector.ENTITY_TYPES,
    "github": GitHubLiveConnector.ENTITY_TYPES,
    "confluence": ConfluenceLiveConnector.ENTITY_TYPES,
    "jira": JiraLiveConnector.ENTITY_TYPES,
    "teams": TeamsLiveConnector.ENTITY_TYPES,
}


class CreateConnectorConnectionRequest(BaseModel):
    source_system: str
    instance_id: str
    display_name: str
    mode: str = "fixture"
    config: dict[str, Any] = {}
    credential: str | None = None


class TestConnectionRequest(BaseModel):
    source_system: str
    mode: str = "fixture"
    config: dict[str, Any] = {}
    credential: str | None = None


class TestConnectionResponse(BaseModel):
    success: bool
    message: str
    containers: list[str] = []
    duration_seconds: float
    error_category: str | None = None


class SyncTriggerResponse(BaseModel):
    run_id: UUID
    status: str
    nodes_upserted: int
    nodes_tombstoned: int
    edges_created: int
    duration_seconds: float
    error_category: str | None = None
    error_detail: str | None = None


class EnrichTriggerResponse(BaseModel):
    nodes_scanned: int
    abstracts_generated: int
    embeddings_generated: int
    skipped_unchanged: int
    skipped_not_synced: int
    errors: int
    duration_seconds: float


@router.get("", response_model=list[ConnectorConnectionSummary])
async def list_connectors(session: AsyncSession = Depends(get_session)) -> Any:
    return await ConnectorConnectionRepository(session).list_all()


@router.get("/entity-types")
async def list_entity_types() -> dict[str, dict[str, str]]:
    """What each live connector can pull, for the "what to pull"
    checkboxes on the connection-creation form — keyed by source_system,
    each value a {entity_type_key: UI label} map. Selections land in
    config.entity_types on the saved connection."""
    return ENTITY_TYPES_BY_SOURCE


class BrowseRequest(BaseModel):
    source_system: str
    mode: str = "live"
    config: dict[str, Any] = {}
    credential: str | None = None


class BrowseContainer(BaseModel):
    native_id: str
    name: str


class BrowseResponse(BaseModel):
    containers: list[BrowseContainer] = []


@router.post("/browse", response_model=BrowseResponse)
async def browse_connector(body: BrowseRequest) -> Any:
    """Lists the pick-able units for a not-yet-saved connection, so the
    UI can offer a checklist instead of defaulting to "sync everything"
    (docs/UI.md "Connectors")."""
    return await _browse(body.source_system, body.mode, body.config, body.credential)


@router.post("/{connection_id}/browse", response_model=BrowseResponse)
async def browse_existing_connection(
    connection_id: UUID, session: AsyncSession = Depends(get_session)
) -> Any:
    """Same, for an already-saved connection — decrypts its stored
    credential rather than asking the user to re-enter it, so the
    container picker can be revisited after creation (docs/UI.md
    "Connectors")."""
    conn_repo = ConnectorConnectionRepository(session)
    connection = await conn_repo.get(connection_id)
    if connection is None:
        raise HTTPException(404, "connector connection not found")

    credential = None
    if connection.mode == "live":
        ciphertext = await conn_repo.get_credential_ciphertext(connection_id)
        settings = Settings()
        if ciphertext is None or not settings.CF_SECRET_KEY:
            raise HTTPException(400, "this connection has no usable stored credential")
        credential = decrypt_credential(ciphertext, settings.CF_SECRET_KEY)

    return await _browse(connection.source_system, connection.mode, connection.config, credential)


async def _browse(
    source_system: str, mode: str, config: dict[str, Any], credential: str | None
) -> BrowseResponse:
    """For Azure DevOps the pick-able unit is projects
    (discover_containers's own output); GitHub's only top-level container
    is the org/user itself, so the pick-able unit there is repos, one
    level under it via list_children."""
    connector = _build_connector(source_system, mode, config, credential)
    try:
        containers = await connector.discover_containers()
        items: list[Any] = list(containers)
        if source_system == "github" and containers:
            page = await connector.list_children(containers[0].native_id)
            items = list(page.items)
        return BrowseResponse(
            containers=[BrowseContainer(native_id=i.native_id, name=i.name) for i in items]
        )
    except ConnectorError as exc:
        raise HTTPException(400, str(exc)) from exc
    finally:
        if hasattr(connector, "aclose"):
            await connector.aclose()  # type: ignore[attr-defined]


@router.post("", response_model=ConnectorConnectionSummary, status_code=201)
async def create_connector(
    body: CreateConnectorConnectionRequest, session: AsyncSession = Depends(get_session)
) -> Any:
    repo = ConnectorConnectionRepository(session)
    existing = await repo.get_by_identity(body.source_system, body.instance_id)
    if existing is not None:
        raise HTTPException(
            409, f"connection {body.source_system}/{body.instance_id} already exists"
        )

    if body.mode == "live":
        missing = [
            f for f in LIVE_CONFIG_FIELDS.get(body.source_system, []) if not body.config.get(f)
        ]
        if missing:
            raise HTTPException(400, f"config.{missing[0]} is required for live connections")
        if not body.credential:
            raise HTTPException(400, "credential is required for live connections")

    ciphertext = None
    if body.credential:
        settings = Settings()
        if not settings.CF_SECRET_KEY:
            raise HTTPException(500, "CF_SECRET_KEY is not configured — cannot store a credential")
        ciphertext = encrypt_credential(body.credential, settings.CF_SECRET_KEY)

    return await repo.create(
        source_system=body.source_system,
        instance_id=body.instance_id,
        display_name=body.display_name,
        mode=body.mode,
        config=body.config,
        credential_ciphertext=ciphertext,
        now=datetime.now(UTC),
    )


class UpdateConnectorConfigRequest(BaseModel):
    config: dict[str, Any]
    display_name: str | None = None


@router.patch("/{connection_id}", response_model=ConnectorConnectionSummary)
async def update_connector_config(
    connection_id: UUID,
    body: UpdateConnectorConfigRequest,
    session: AsyncSession = Depends(get_session),
) -> Any:
    """Changes a connection's config (entity types, container/repo
    selection, org URL, repo visibility, ...) and optionally its display
    name, without recreating it — e.g. turning on Pull Requests after
    the fact so already-unresolved link-extraction targets
    (docs/CONNECTORS.md "Link extraction") can resolve on the next sync.
    Mode and the stored credential are untouched — this never accepts a
    new PAT."""
    repo = ConnectorConnectionRepository(session)
    existing = await repo.get(connection_id)
    if existing is None:
        raise HTTPException(404, "connector connection not found")

    if existing.mode == "live":
        missing = [
            f for f in LIVE_CONFIG_FIELDS.get(existing.source_system, []) if not body.config.get(f)
        ]
        if missing:
            raise HTTPException(400, f"config.{missing[0]} is required for live connections")

    updated = await repo.update_config(
        connection_id, body.config, datetime.now(UTC), display_name=body.display_name
    )
    if updated is None:
        raise HTTPException(404, "connector connection not found")
    return updated


class RotateCredentialRequest(BaseModel):
    credential: str


@router.post("/{connection_id}/rotate-credential", response_model=ConnectorConnectionSummary)
async def rotate_connector_credential(
    connection_id: UUID, body: RotateCredentialRequest, session: AsyncSession = Depends(get_session)
) -> Any:
    """Replaces the stored credential (e.g. a re-scoped PAT) in place —
    config and the connection's identity are untouched. Complements
    update_connector_config above, which deliberately never touches the
    credential."""
    repo = ConnectorConnectionRepository(session)
    existing = await repo.get(connection_id)
    if existing is None:
        raise HTTPException(404, "connector connection not found")

    settings = Settings()
    if not settings.CF_SECRET_KEY:
        raise HTTPException(500, "CF_SECRET_KEY is not configured — cannot store a credential")
    ciphertext = encrypt_credential(body.credential, settings.CF_SECRET_KEY)

    updated = await repo.update_credential(connection_id, ciphertext, datetime.now(UTC))
    if updated is None:
        raise HTTPException(404, "connector connection not found")
    return updated


@router.delete("/{connection_id}", status_code=204)
async def delete_connector(
    connection_id: UUID, session: AsyncSession = Depends(get_session)
) -> None:
    """Deletes the connection and its stored credential. Technical nodes
    already synced through it are left in the catalog — this stops
    future syncs, it doesn't purge history (docs/UI.md "Connectors")."""
    await ConnectorConnectionRepository(session).delete(connection_id)


@router.post("/test", response_model=TestConnectionResponse)
async def test_connection_before_save(body: TestConnectionRequest) -> Any:
    """Tests credentials/config *before* anything is saved — the form's
    "Test Connection" button. Makes one real, cheap authenticated call
    (discover_containers) against the actual source and reports what
    came back, or exactly what went wrong (invalid PAT, wrong org,
    network issue, rate limited) via the same error categories every
    other connector error uses."""
    return await _test_connection(body.source_system, body.mode, body.config, body.credential)


@router.post("/{connection_id}/test", response_model=TestConnectionResponse)
async def test_existing_connection(
    connection_id: UUID, session: AsyncSession = Depends(get_session)
) -> Any:
    """Re-tests an already-saved connection — decrypts its stored
    credential to do so, never returns it."""
    conn_repo = ConnectorConnectionRepository(session)
    connection = await conn_repo.get(connection_id)
    if connection is None:
        raise HTTPException(404, "connector connection not found")

    credential = None
    if connection.mode == "live":
        ciphertext = await conn_repo.get_credential_ciphertext(connection_id)
        settings = Settings()
        if ciphertext is None or not settings.CF_SECRET_KEY:
            raise HTTPException(400, "this connection has no usable stored credential")
        credential = decrypt_credential(ciphertext, settings.CF_SECRET_KEY)

    return await _test_connection(
        connection.source_system, connection.mode, connection.config, credential
    )


async def _test_connection(
    source_system: str, mode: str, config: dict[str, Any], credential: str | None
) -> TestConnectionResponse:
    started = time.monotonic()
    connector: SourceConnector | None = None
    try:
        connector = _build_connector(source_system, mode, config, credential)
        containers = await connector.discover_containers()
        return TestConnectionResponse(
            success=True,
            message=f"Connected — found {len(containers)} top-level container(s).",
            containers=[c.name for c in containers],
            duration_seconds=round(time.monotonic() - started, 2),
        )
    except ConnectorError as exc:
        return TestConnectionResponse(
            success=False,
            message=str(exc),
            duration_seconds=round(time.monotonic() - started, 2),
            error_category=exc.category.value,
        )
    finally:
        if connector is not None and hasattr(connector, "aclose"):
            await connector.aclose()  # type: ignore[attr-defined]


@router.get("/health")
async def connector_health(session: AsyncSession = Depends(get_session)) -> list[dict[str, Any]]:
    """Per-connection sync freshness — the signal this session's own
    debugging kept having to reconstruct by hand (checking sync_run rows
    directly): Confluence failed with a 403 and nothing surfaced that to
    anyone until someone happened to look. `SyncState` already recorded
    the truth the whole time; this is just the read path that turns it
    into "is this connection stale, and since when."

    `stale` is `last_successful_sync` older than 2x the scheduler
    interval (docs: synchronization/scheduler.py) — twice, not once, so a
    single slow tick isn't misreported as broken. If the scheduler is
    disabled (CF_SYNC_INTERVAL_SECONDS=0), a fixed 24h threshold applies
    instead, since there's no interval to derive one from.
    """
    settings = Settings()
    threshold_seconds = (
        settings.CF_SYNC_INTERVAL_SECONDS * 2 if settings.CF_SYNC_INTERVAL_SECONDS > 0 else 86400
    )
    now = datetime.now(UTC)

    connections = await ConnectorConnectionRepository(session).list_all()
    states_by_key = {
        (s.source_system, s.scope_id): s
        for s in await SyncStateRepository(session).list_all()
    }

    out: list[dict[str, Any]] = []
    for conn in connections:
        state = states_by_key.get((conn.source_system, conn.instance_id))
        last_success = state.last_successful_sync if state else None
        age_seconds = (now - last_success).total_seconds() if last_success else None
        out.append(
            {
                "connection_id": str(conn.id),
                "source_system": conn.source_system,
                "instance_id": conn.instance_id,
                "display_name": conn.display_name,
                "status": state.status.value if state else "NEVER_SYNCED",
                "last_successful_sync": last_success.isoformat() if last_success else None,
                "last_reconciliation": (
                    state.last_reconciliation.isoformat()
                    if state and state.last_reconciliation
                    else None
                ),
                "error": state.error if state else None,
                "stale": age_seconds is None or age_seconds > threshold_seconds,
            }
        )
    return out


@router.get("/{connection_id}/sync-runs")
async def list_sync_runs(
    connection_id: UUID, session: AsyncSession = Depends(get_session)
) -> list[dict[str, Any]]:
    conn_repo = ConnectorConnectionRepository(session)
    connection = await conn_repo.get(connection_id)
    if connection is None:
        raise HTTPException(404, "connector connection not found")

    run_repo = SyncRunRepository(session)
    runs = await run_repo.list_for_scope(connection.source_system, connection.instance_id)
    return [
        {
            "id": str(r.id),
            "status": r.status.value,
            "started_at": r.started_at.isoformat(),
            "finished_at": r.finished_at.isoformat() if r.finished_at else None,
            "nodes_upserted": r.nodes_upserted,
            "nodes_tombstoned": r.nodes_tombstoned,
            "edges_created": r.edges_created,
            "error_category": r.error_category.value if r.error_category else None,
            "error_detail": r.error_detail,
        }
        for r in runs
    ]


@router.post("/{connection_id}/sync", response_model=SyncTriggerResponse)
async def trigger_sync(
    connection_id: UUID,
    mode: SyncMode = "full",
    session: AsyncSession = Depends(get_session),
) -> Any:
    """Runs synchronously and returns once the sync completes — the
    caller sees exactly how long extraction took (docs/UI.md's
    Connectors screen shows this as request latency). A background-task +
    polling design is the more scalable shape for a large org; this is
    the simpler one, chosen so sync duration is directly observable.

    `mode=incremental` uses the connector's own `list_changed_since` when
    it has one (today: Azure DevOps work items — see its docstring),
    falling back to a full pass, logged, when it doesn't
    (synchronization/orchestrator.py's `sync_source`)."""
    conn_repo = ConnectorConnectionRepository(session)
    connection = await conn_repo.get(connection_id)
    if connection is None:
        raise HTTPException(404, "connector connection not found")

    credential = None
    if connection.mode == "live":
        ciphertext = await conn_repo.get_credential_ciphertext(connection_id)
        settings = Settings()
        if ciphertext is None or not settings.CF_SECRET_KEY:
            raise HTTPException(400, "this connection has no usable stored credential")
        credential = decrypt_credential(ciphertext, settings.CF_SECRET_KEY)

    connector = _build_connector(
        connection.source_system, connection.mode, connection.config, credential
    )

    started = time.monotonic()
    try:
        run = await sync_source(
            session, connector, source_instance_id=connection.instance_id, mode=mode
        )
    except ConnectorError:
        # sync_source records the failed SyncRun (error category + detail)
        # before re-raising (docs/CONNECTORS.md) — the API's job is to
        # report that recorded failure as a normal response, not let it
        # surface as an unhandled 500. list_for_scope is ordered newest
        # first, so [0] is the run this call just failed.
        runs = await SyncRunRepository(session).list_for_scope(
            connection.source_system, connection.instance_id
        )
        if not runs:
            raise
        run = runs[0]
    finally:
        if hasattr(connector, "aclose"):
            await connector.aclose()  # type: ignore[attr-defined]
    duration = time.monotonic() - started

    return SyncTriggerResponse(
        run_id=run.id,
        status=run.status.value,
        nodes_upserted=run.nodes_upserted,
        nodes_tombstoned=run.nodes_tombstoned,
        edges_created=run.edges_created,
        duration_seconds=round(duration, 2),
        error_category=run.error_category.value if run.error_category else None,
        error_detail=run.error_detail,
    )



@router.post("/{connection_id}/enrich", response_model=EnrichTriggerResponse)
async def trigger_enrichment(
    connection_id: UUID,
    force: bool = False,
    session: AsyncSession = Depends(get_session),
) -> Any:
    """On-demand search-metadata generation — never run by sync itself
    (ADR-003), never touching `get_context_pack`'s deterministic path.

    Confluence gets LLM abstracts + keywords (ADR-010,
    enrichment/confluence_abstracts.py) *and* embeddings, since it's the
    one connector with no vendor-supplied description at all. Every other
    connector (Azure DevOps, GitHub, Jira) gets embeddings only
    (enrichment/node_embeddings.py) — they already carry real
    names/descriptions, so the abstract-generation gap doesn't apply the
    same way; only the semantic-search coverage does.

    Requires Ollama running locally (CF_OLLAMA_BASE_URL/CF_OLLAMA_MODEL/
    CF_OLLAMA_EMBED_MODEL)."""
    conn_repo = ConnectorConnectionRepository(session)
    connection = await conn_repo.get(connection_id)
    if connection is None:
        raise HTTPException(404, "connector connection not found")
    if connection.source_system not in ("confluence", "azure_devops", "github", "jira"):
        raise HTTPException(
            400, f"enrichment is not implemented for {connection.source_system!r}"
        )

    credential = None
    if connection.mode == "live":
        ciphertext = await conn_repo.get_credential_ciphertext(connection_id)
        settings = Settings()
        if ciphertext is None or not settings.CF_SECRET_KEY:
            raise HTTPException(400, "this connection has no usable stored credential")
        credential = decrypt_credential(ciphertext, settings.CF_SECRET_KEY)

    connector = _build_connector(
        connection.source_system, connection.mode, connection.config, credential
    )
    settings = Settings()
    ollama = OllamaClient(settings.CF_OLLAMA_BASE_URL, settings.CF_OLLAMA_MODEL)

    started = time.monotonic()
    try:
        if connection.source_system == "confluence":
            page_stats = await enrich_confluence_pages(
                connector,
                NodeRepository(session),
                ollama,
                source_instance_id=connection.instance_id,
                embed_model=settings.CF_OLLAMA_EMBED_MODEL,
                force=force,
            )
            response = EnrichTriggerResponse(
                nodes_scanned=page_stats.pages_scanned,
                abstracts_generated=page_stats.abstracts_generated,
                embeddings_generated=page_stats.embeddings_generated,
                skipped_unchanged=page_stats.skipped_unchanged,
                skipped_not_synced=page_stats.skipped_not_synced,
                errors=page_stats.errors,
                duration_seconds=0.0,
            )
        else:
            node_stats = await enrich_node_embeddings(
                connector,
                NodeRepository(session),
                ollama,
                source_instance_id=connection.instance_id,
                embed_model=settings.CF_OLLAMA_EMBED_MODEL,
                force=force,
            )
            response = EnrichTriggerResponse(
                nodes_scanned=node_stats.nodes_scanned,
                abstracts_generated=0,
                embeddings_generated=node_stats.embeddings_generated,
                skipped_unchanged=node_stats.skipped_unchanged,
                skipped_not_synced=node_stats.skipped_not_synced,
                errors=node_stats.errors,
                duration_seconds=0.0,
            )
    except ConnectorError as exc:
        raise HTTPException(400, str(exc)) from exc
    finally:
        await ollama.aclose()
        if hasattr(connector, "aclose"):
            await connector.aclose()  # type: ignore[attr-defined]
    response.duration_seconds = round(time.monotonic() - started, 2)
    return response


def _build_connector(
    source_system: str, mode: str, config: dict[str, Any], credential: str | None
) -> SourceConnector:
    if mode == "fixture":
        return get_fixture_connector_class(source_system)()  # type: ignore[return-value]

    if not credential:
        raise HTTPException(400, "credential is required for live connections")

    # Same ABC-vs-Protocol mypy gap noted elsewhere (cli/main.py) —
    # AzureDevOpsLiveConnector/GitHubLiveConnector structurally satisfy
    # SourceConnector at runtime; mypy can't see it through the class
    # variable vs instance variable + Literal-narrowing indirection.
    entity_types = config.get("entity_types") or None
    selected_containers = config.get("selected_containers") or None

    if source_system == "azure_devops":
        org_url = config.get("org_url")
        if not org_url:
            raise HTTPException(400, "config.org_url is required for azure_devops live connections")
        build_retention_count = config.get("build_retention_count")
        return AzureDevOpsLiveConnector(  # type: ignore[return-value]
            org_url,
            pat=credential,
            entity_types=entity_types,
            selected_containers=selected_containers,
            **({"build_retention_count": build_retention_count} if build_retention_count else {}),
        )

    if source_system == "github":
        org = config.get("org")
        if not org:
            raise HTTPException(400, "config.org is required for github live connections")
        return GitHubLiveConnector(  # type: ignore[return-value]
            org,
            token=credential,
            entity_types=entity_types,
            selected_containers=selected_containers,
            repo_visibility=config.get("repo_visibility") or "all",
        )

    if source_system == "confluence":
        site_url = config.get("site_url")
        email = config.get("email")
        if not site_url or not email:
            raise HTTPException(
                400, "config.site_url and config.email are required for confluence live connections"
            )
        return ConfluenceLiveConnector(  # type: ignore[return-value]
            site_url,
            email=email,
            api_token=credential,
            entity_types=entity_types,
            selected_containers=selected_containers,
        )

    if source_system == "jira":
        site_url = config.get("site_url")
        email = config.get("email")
        if not site_url or not email:
            raise HTTPException(
                400, "config.site_url and config.email are required for jira live connections"
            )
        return JiraLiveConnector(  # type: ignore[return-value]
            site_url,
            email=email,
            api_token=credential,
            entity_types=entity_types,
            selected_containers=selected_containers,
        )

    if source_system == "teams":
        tenant_id = config.get("tenant_id")
        team_id = config.get("team_id")
        client_id = config.get("client_id")
        if not tenant_id or not team_id or not client_id:
            raise HTTPException(
                400,
                "config.tenant_id, config.team_id, and config.client_id are required for "
                "teams live connections",
            )
        return TeamsLiveConnector(  # type: ignore[return-value]
            tenant_id,
            team_id=team_id,
            client_id=client_id,
            client_secret=credential,
            entity_types=entity_types,
            selected_containers=selected_containers,
        )

    raise HTTPException(400, f"no live connector implemented for source_system={source_system!r}")
