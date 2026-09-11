"""EvidenceRepository."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from context_fabric.domain.evidence import Evidence
from context_fabric.persistence.orm.evidence import EvidenceORM


def _to_domain(row: EvidenceORM) -> Evidence:
    return Evidence(
        id=row.id,
        node_id=row.node_id,
        source_system=row.source_system,
        source_instance_id=row.source_instance_id,
        native_id=row.native_id,
        source_version=row.source_version,
        uri=row.uri,
        content_hash=row.content_hash,
        acl_ref=row.acl_ref,
        retrieved_at=row.retrieved_at,
    )


class EvidenceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, evidence: Evidence) -> Evidence:
        row = EvidenceORM(
            id=evidence.id,
            node_id=evidence.node_id,
            source_system=evidence.source_system,
            source_instance_id=evidence.source_instance_id,
            native_id=evidence.native_id,
            source_version=evidence.source_version,
            uri=evidence.uri,
            content_hash=evidence.content_hash,
            acl_ref=evidence.acl_ref,
            retrieved_at=evidence.retrieved_at,
        )
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return _to_domain(row)

    async def get(self, evidence_id: UUID) -> Evidence | None:
        row = await self._session.get(EvidenceORM, evidence_id)
        return _to_domain(row) if row is not None else None

    async def list_for_node(self, node_id: UUID) -> list[Evidence]:
        stmt = select(EvidenceORM).where(EvidenceORM.node_id == node_id)
        rows = (await self._session.execute(stmt)).scalars().all()
        return [_to_domain(r) for r in rows]
