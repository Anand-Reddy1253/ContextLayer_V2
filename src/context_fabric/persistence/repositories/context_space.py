"""ContextSpaceRepository — ContextSpace + its Binding rows."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from context_fabric.domain.context_space import Binding, ContextSpace
from context_fabric.domain.enums import Capability, EdgeOrigin
from context_fabric.persistence.orm.context_space import BindingORM, ContextSpaceORM


def _binding_to_domain(row: BindingORM) -> Binding:
    return Binding(
        id=row.id,
        context_space_id=row.context_space_id,
        capability=Capability(row.capability),
        source_system=row.source_system,
        source_instance_id=row.source_instance_id,
        native_container=row.native_container,
        origin=EdgeOrigin(row.origin),
        priority=row.priority,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _context_space_to_domain(row: ContextSpaceORM, bindings: list[BindingORM]) -> ContextSpace:
    return ContextSpace(
        id=row.id,
        name=row.name,
        description=row.description,
        owners=row.owners,
        product=row.product,
        teams=row.teams,
        services=row.services,
        status=row.status,  # type: ignore[arg-type]
        version=row.version,
        created_at=row.created_at,
        updated_at=row.updated_at,
        business_node_id=row.business_node_id,
        bindings=[_binding_to_domain(b) for b in bindings],
    )


class ContextSpaceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, space: ContextSpace) -> ContextSpace:
        row = ContextSpaceORM(
            id=space.id,
            business_node_id=space.business_node_id,
            name=space.name,
            description=space.description,
            owners=space.owners,
            product=space.product,
            teams=space.teams,
            services=space.services,
            status=space.status,
            version=space.version,
            created_at=space.created_at,
            updated_at=space.updated_at,
        )
        self._session.add(row)
        # Flushed before the bindings, not batched with them: there is no
        # ORM relationship() between ContextSpaceORM and BindingORM (see
        # module docstring), so SQLAlchemy has no dependency information
        # to order the two inserts correctly within a single flush — an
        # integration test caught this as a real FK-violation race.
        await self._session.flush()

        binding_rows = [
            BindingORM(
                id=b.id,
                context_space_id=space.id,
                capability=b.capability.value,
                source_system=b.source_system,
                source_instance_id=b.source_instance_id,
                native_container=b.native_container,
                origin=b.origin.value,
                priority=b.priority,
                created_at=b.created_at,
                updated_at=b.updated_at,
            )
            for b in space.bindings
        ]
        for b_row in binding_rows:
            self._session.add(b_row)
        await self._session.flush()
        return await self.get(space.id)  # type: ignore[return-value]

    async def get(self, context_space_id: str) -> ContextSpace | None:
        stmt = select(ContextSpaceORM).where(ContextSpaceORM.id == context_space_id)
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        if row is None:
            return None
        bindings_stmt = select(BindingORM).where(BindingORM.context_space_id == context_space_id)
        bindings = (await self._session.execute(bindings_stmt)).scalars().all()
        return _context_space_to_domain(row, list(bindings))

    async def list_all(self) -> list[ContextSpace]:
        rows = (await self._session.execute(select(ContextSpaceORM))).scalars().all()
        spaces = []
        for row in rows:
            bindings_stmt = select(BindingORM).where(BindingORM.context_space_id == row.id)
            bindings = (await self._session.execute(bindings_stmt)).scalars().all()
            spaces.append(_context_space_to_domain(row, list(bindings)))
        return spaces

    async def add_binding(self, binding: Binding) -> Binding:
        row = BindingORM(
            id=binding.id,
            context_space_id=binding.context_space_id,
            capability=binding.capability.value,
            source_system=binding.source_system,
            source_instance_id=binding.source_instance_id,
            native_container=binding.native_container,
            origin=binding.origin.value,
            priority=binding.priority,
            created_at=binding.created_at,
            updated_at=binding.updated_at,
        )
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return _binding_to_domain(row)

    async def update_binding(self, binding: Binding) -> Binding:
        row = await self._session.get(BindingORM, binding.id)
        if row is None:
            raise ValueError(f"cannot update: no binding with id={binding.id}")
        row.capability = binding.capability.value
        row.source_system = binding.source_system
        row.source_instance_id = binding.source_instance_id
        row.native_container = binding.native_container
        row.origin = binding.origin.value
        row.priority = binding.priority
        row.updated_at = binding.updated_at
        await self._session.flush()
        await self._session.refresh(row)
        return _binding_to_domain(row)

    async def remove_binding(self, binding_id: UUID) -> None:
        row = await self._session.get(BindingORM, binding_id)
        if row is not None:
            await self._session.delete(row)
            await self._session.flush()

    async def delete(self, context_space_id: str) -> None:
        """Deletes the ContextSpace row; its bindings cascade via
        binding.context_space_id's ondelete="CASCADE" FK (migration 0005)
        — no separate binding cleanup needed here."""
        row = await self._session.get(ContextSpaceORM, context_space_id)
        if row is not None:
            await self._session.delete(row)
            await self._session.flush()
