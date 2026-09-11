"""ContextSpace + Binding write path (docs/DOMAIN_MODEL.md "ContextSpace",
"Binding"). Domain-typed in, domain-typed out, backed by
persistence/repositories/context_space.py — the config-file-driven
equivalent of what the Phase 16 UI form will do.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import yaml

from context_fabric.catalog.business_tree import get_by_business_path
from context_fabric.domain.context_space import Binding, ContextSpace
from context_fabric.domain.enums import Capability, EdgeOrigin
from context_fabric.persistence.repositories.context_space import ContextSpaceRepository
from context_fabric.persistence.repositories.node import NodeRepository

CONTEXT_SPACE_CONFIGS_DIR = Path(__file__).resolve().parents[3] / "configs" / "context-spaces"


class BusinessRefUnresolved(ValueError):
    """Raised when a context-space config's business_ref.path doesn't
    resolve to a seeded business node — seed the business tree first
    (catalog.business_tree.seed_business_tree)."""


def load_context_space_config(path: Path) -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data


def find_context_space_config_by_id(
    context_space_id: str, configs_dir: Path | None = None
) -> Path | None:
    """Context-space ids ("talentflow/identity") don't map 1:1 onto config
    filenames ("talentflow-identity.yaml") — scans every *.yaml in the
    directory for a matching `id` field rather than guessing a filename."""
    directory = configs_dir or CONTEXT_SPACE_CONFIGS_DIR
    for candidate in sorted(directory.glob("*.yaml")):
        data = load_context_space_config(candidate)
        if data.get("id") == context_space_id:
            return candidate
    return None


def _binding_from_config(context_space_id: str, raw: dict[str, Any], now: datetime) -> Binding:
    return Binding(
        context_space_id=context_space_id,
        capability=Capability(raw["capability"]),
        source_system=raw["source_system"],
        source_instance_id=raw["source_instance_id"],
        native_container=raw["native_container"],
        origin=EdgeOrigin(raw.get("origin", "HUMAN")),
        priority=raw.get("priority", 0),
        created_at=now,
        updated_at=now,
    )


async def create_context_space(
    context_space_repo: ContextSpaceRepository,
    node_repo: NodeRepository,
    config: dict[str, Any],
) -> ContextSpace:
    """Builds a ContextSpace + Bindings from a parsed
    configs/context-spaces/*.yaml document and persists it."""
    business_ref = config["business_ref"]
    business_node = await get_by_business_path(node_repo, business_ref["path"])
    if business_node is None:
        raise BusinessRefUnresolved(
            f"business_ref path {business_ref['path']!r} does not resolve to a business node"
        )

    now = datetime.now(UTC)
    space = ContextSpace(
        id=config["id"],
        name=config["name"],
        description=config.get("description", ""),
        owners=config.get("owners", []),
        product=config.get("product"),
        teams=config.get("teams", []),
        services=config.get("services", []),
        status=config.get("status", "active"),
        version=config.get("version", 1),
        created_at=now,
        updated_at=now,
        business_node_id=business_node.id,
        bindings=[
            _binding_from_config(config["id"], raw, now) for raw in config.get("bindings", [])
        ],
    )
    return await context_space_repo.create(space)


async def create_context_space_from_fields(
    context_space_repo: ContextSpaceRepository,
    *,
    id: str,
    name: str,
    description: str,
    business_node_id: UUID,
    owners: list[str] | None = None,
    product: str | None = None,
    teams: list[str] | None = None,
    services: list[str] | None = None,
) -> ContextSpace:
    """Same as create_context_space, but for the UI form: the caller
    already resolved business_node_id (e.g. from a dropdown), so there's
    no business_ref.path lookup here — that indirection exists only for
    the YAML-config import path."""
    now = datetime.now(UTC)
    space = ContextSpace(
        id=id,
        name=name,
        description=description,
        owners=owners or [],
        product=product,
        teams=teams or [],
        services=services or [],
        created_at=now,
        updated_at=now,
        business_node_id=business_node_id,
    )
    return await context_space_repo.create(space)


async def get_context_space(
    context_space_repo: ContextSpaceRepository, context_space_id: str
) -> ContextSpace | None:
    return await context_space_repo.get(context_space_id)


async def list_context_spaces(context_space_repo: ContextSpaceRepository) -> list[ContextSpace]:
    return await context_space_repo.list_all()


async def delete_context_space(
    context_space_repo: ContextSpaceRepository, context_space_id: str
) -> None:
    """Deletes a context space and every one of its bindings (FK cascade
    — docs/persistence.md "binding"). Never touches the business node it
    was anchored to, or any synced technical node its bindings pointed
    at — only the logical-layer correlation itself."""
    await context_space_repo.delete(context_space_id)


async def add_binding(
    context_space_repo: ContextSpaceRepository,
    context_space_id: str,
    *,
    capability: Capability,
    source_system: str,
    source_instance_id: str,
    native_container: str,
    origin: EdgeOrigin = EdgeOrigin.HUMAN,
    priority: int = 0,
) -> Binding:
    now = datetime.now(UTC)
    binding = Binding(
        context_space_id=context_space_id,
        capability=capability,
        source_system=source_system,
        source_instance_id=source_instance_id,
        native_container=native_container,
        origin=origin,
        priority=priority,
        created_at=now,
        updated_at=now,
    )
    return await context_space_repo.add_binding(binding)


async def update_binding(context_space_repo: ContextSpaceRepository, binding: Binding) -> Binding:
    updated = binding.model_copy(update={"updated_at": datetime.now(UTC)})
    return await context_space_repo.update_binding(updated)


async def remove_binding(context_space_repo: ContextSpaceRepository, binding_id: UUID) -> None:
    await context_space_repo.remove_binding(binding_id)


@dataclass
class BindingReconciliation:
    binding: Binding
    resolved: bool
    node_id: UUID | None = None


@dataclass
class ReconcileReport:
    context_space_id: str
    results: list[BindingReconciliation]

    @property
    def all_resolved(self) -> bool:
        return all(r.resolved for r in self.results)


async def reconcile_context_space(
    node_repo: NodeRepository, space: ContextSpace
) -> ReconcileReport:
    """Confirms each binding's native_container actually resolves to a
    synced technical node (docs/phases/PHASE-08.md) — a binding whose
    source was never synced (or whose connector doesn't exist, e.g.
    Confluence) resolves to False, reported clearly, never a crash."""
    results = []
    for binding in space.bindings:
        node = await node_repo.get_by_technical_identity(
            binding.source_system, binding.source_instance_id, binding.native_container
        )
        results.append(
            BindingReconciliation(
                binding=binding, resolved=node is not None, node_id=node.id if node else None
            )
        )
    return ReconcileReport(context_space_id=space.id, results=results)
