"""ConnectorConnectionRepository.

Every read path returns a domain type that deliberately has no
`credential_ciphertext` field — the raw ciphertext never leaves this
module. Decryption for actual connector use is a connectors/ concern
(Phase 19), out of scope here; this repository only stores/retrieves the
opaque ciphertext bytes for that later use (docs/SECURITY.md).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from context_fabric.persistence.orm.connector_connection import ConnectorConnectionORM


class ConnectorConnectionSummary(BaseModel):
    """What's safe to hand back to any caller — never the ciphertext."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    source_system: str
    instance_id: str
    display_name: str
    mode: str
    config: dict
    created_at: datetime
    updated_at: datetime


def _to_summary(row: ConnectorConnectionORM) -> ConnectorConnectionSummary:
    return ConnectorConnectionSummary(
        id=row.id,
        source_system=row.source_system,
        instance_id=row.instance_id,
        display_name=row.display_name,
        mode=row.mode,
        config=row.config,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class ConnectorConnectionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        source_system: str,
        instance_id: str,
        display_name: str,
        mode: str,
        config: dict,
        credential_ciphertext: bytes | None,
        now: datetime,
    ) -> ConnectorConnectionSummary:
        row = ConnectorConnectionORM(
            id=uuid4(),
            source_system=source_system,
            instance_id=instance_id,
            display_name=display_name,
            mode=mode,
            config=config,
            credential_ciphertext=credential_ciphertext,
            created_at=now,
            updated_at=now,
        )
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return _to_summary(row)

    async def get(self, connection_id: UUID) -> ConnectorConnectionSummary | None:
        row = await self._session.get(ConnectorConnectionORM, connection_id)
        return _to_summary(row) if row is not None else None

    async def get_by_identity(
        self, source_system: str, instance_id: str
    ) -> ConnectorConnectionSummary | None:
        stmt = select(ConnectorConnectionORM).where(
            ConnectorConnectionORM.source_system == source_system,
            ConnectorConnectionORM.instance_id == instance_id,
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return _to_summary(row) if row is not None else None

    async def list_all(self) -> list[ConnectorConnectionSummary]:
        rows = (await self._session.execute(select(ConnectorConnectionORM))).scalars().all()
        return [_to_summary(r) for r in rows]

    async def update_config(
        self,
        connection_id: UUID,
        config: dict,
        now: datetime,
        *,
        display_name: str | None = None,
    ) -> ConnectorConnectionSummary | None:
        """Changes `config` (e.g. which entity types/containers to pull,
        or the org URL) and optionally `display_name` — mode and the
        stored credential are untouched here (credential rotation isn't
        this method's job). Returns None if the connection doesn't exist
        rather than raising, matching this repository's other lookup
        methods."""
        row = await self._session.get(ConnectorConnectionORM, connection_id)
        if row is None:
            return None
        row.config = config
        if display_name is not None:
            row.display_name = display_name
        row.updated_at = now
        await self._session.flush()
        await self._session.refresh(row)
        return _to_summary(row)

    async def update_credential(
        self, connection_id: UUID, credential_ciphertext: bytes, now: datetime
    ) -> ConnectorConnectionSummary | None:
        """Rotates the stored credential (e.g. a new/rescoped PAT) without
        touching config or recreating the connection. Returns None if the
        connection doesn't exist, matching this repository's other lookup
        methods."""
        row = await self._session.get(ConnectorConnectionORM, connection_id)
        if row is None:
            return None
        row.credential_ciphertext = credential_ciphertext
        row.updated_at = now
        await self._session.flush()
        await self._session.refresh(row)
        return _to_summary(row)

    async def get_credential_ciphertext(self, connection_id: UUID) -> bytes | None:
        """The one method in this repository that touches the raw
        ciphertext — used only by connectors/ (via api/routes/connectors.py's
        sync trigger) to decrypt for an actual live connector call. Never
        exposed through ConnectorConnectionSummary."""
        row = await self._session.get(ConnectorConnectionORM, connection_id)
        return row.credential_ciphertext if row is not None else None

    async def delete(self, connection_id: UUID) -> None:
        """Deletes the connection (and its encrypted credential) — never
        touches technical nodes already synced through it. Those stay in
        the catalog, still browsable/bindable, until a future sync
        naturally ages them out; deleting the connection just stops
        future syncs, it isn't a "purge everything this ever synced"
        operation."""
        row = await self._session.get(ConnectorConnectionORM, connection_id)
        if row is not None:
            await self._session.delete(row)
            await self._session.flush()
