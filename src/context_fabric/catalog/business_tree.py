"""Business layer CRUD (docs/architecture.md "Business layer").

Originally scoped as config-seeding only (Phase 8), with full authoring
CRUD reserved for Phase 16's UI. `create_business_node`/`list_business_tree`
were fast-tracked ahead of that phase — the org tree needs a real
create-a-node UI now, not only bulk YAML seeding
(configs/business-tree/*.yaml, still how a fresh environment bootstraps).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import yaml

from context_fabric.domain.enums import Layer
from context_fabric.domain.ltree import sanitize_label
from context_fabric.domain.node import Node
from context_fabric.persistence.repositories.context_space import ContextSpaceRepository
from context_fabric.persistence.repositories.node import NodeRepository

BUSINESS_TREE_CONFIGS_DIR = Path(__file__).resolve().parents[3] / "configs" / "business-tree"


class BusinessNodeHasDependents(ValueError):
    """Raised when a business node can't be deleted because a child node
    or a context space still depends on it — never a silent cascade that
    could orphan a context space's anchor or a subtree of nodes."""


def business_path_to_ltree(business_path: str) -> str:
    """"ACME/Engineering/TalentFlow/Identity" -> "ACME.Engineering.TalentFlow.Identity" """
    return ".".join(sanitize_label(seg) for seg in business_path.split("/"))


def load_business_tree_config(path: Path | None = None) -> dict[str, Any]:
    target = path or (BUSINESS_TREE_CONFIGS_DIR / "acme.yaml")
    data: dict[str, Any] = yaml.safe_load(target.read_text(encoding="utf-8"))
    return data


async def seed_business_tree(
    node_repo: NodeRepository, tree: dict[str, Any], *, parent: Node | None = None
) -> dict[str, Node]:
    """Recursively creates BUSINESS nodes from a nested tree config
    (load_business_tree_config's shape), idempotently — skips creating a
    node that already exists at the same path. Returns {ltree_path: Node}
    for every node in the subtree, so callers can resolve a business path
    to a node id without a second lookup."""
    now = datetime.now(UTC)
    label = sanitize_label(tree["id"])
    path = f"{parent.path}.{label}" if parent is not None else label

    existing = await node_repo.get_by_path(path)
    if existing is None:
        candidate = Node(
            layer=Layer.BUSINESS,
            kind=tree["kind"],
            name=tree.get("name", tree["id"]),
            description=tree.get("description"),
            owners=tree.get("owners", []),
            parent_id=parent.id if parent is not None else None,
            path=path,
            first_seen_at=now,
            last_seen_at=now,
            created_at=now,
            updated_at=now,
        )
        existing = await node_repo.create(candidate)

    results = {path: existing}
    for child in tree.get("children", []):
        results.update(await seed_business_tree(node_repo, child, parent=existing))
    return results


async def get_by_business_path(node_repo: NodeRepository, business_path: str) -> Node | None:
    """business_path like "ACME/Engineering/TalentFlow/Identity" -> the
    BUSINESS node at that ltree path, or None if it hasn't been seeded."""
    return await node_repo.get_by_path(business_path_to_ltree(business_path))


async def list_business_tree(node_repo: NodeRepository) -> list[Node]:
    """Every BUSINESS node, ordered by path (parents before children) —
    the UI builds the tree client-side from this flat, ordered list."""
    return await node_repo.list_by_layer(Layer.BUSINESS)


async def create_business_node(
    node_repo: NodeRepository,
    *,
    parent_id: UUID | None,
    kind: str,
    name: str,
    description: str | None = None,
    owners: list[str] | None = None,
) -> Node:
    """Creates one BUSINESS node under `parent_id` (None for a new root,
    e.g. a second org). Used by api/routes/org.py — the UI's "create
    business node" form, as opposed to seed_business_tree's bulk config
    import."""
    now = datetime.now(UTC)
    if parent_id is not None:
        parent = await node_repo.get(parent_id)
        if parent is None:
            raise ValueError(f"parent node {parent_id} not found")
        if parent.layer is not Layer.BUSINESS:
            raise ValueError(f"parent node {parent_id} is not a BUSINESS node")
        path = f"{parent.path}.{sanitize_label(name)}"
    else:
        path = sanitize_label(name)

    candidate = Node(
        layer=Layer.BUSINESS,
        kind=kind,
        name=name,
        description=description,
        owners=owners or [],
        parent_id=parent_id,
        path=path,
        first_seen_at=now,
        last_seen_at=now,
        created_at=now,
        updated_at=now,
    )
    return await node_repo.create(candidate)


async def update_business_node(
    node_repo: NodeRepository,
    node_id: UUID,
    *,
    name: str | None = None,
    description: str | None = None,
    kind: str | None = None,
    owners: list[str] | None = None,
    attributes: dict[str, Any] | None = None,
) -> Node:
    """Partial update of an existing BUSINESS node — name/description/
    kind/owners (omit to leave unchanged) plus a merge into `attributes`
    (the "business context" fields: criticality_tier, compliance_scope,
    stakeholders, communication_channel — docs/UI.md "Business
    Hierarchy"). `kind` exists mainly to fix a mislabeled node after the
    fact (e.g. a root created as "SQUAD" by mistake) — it does not
    re-validate against KINDS the way create_business_node's caller does,
    since a corrective rename is exactly the case where the original
    value was already wrong. A key present in `attributes` with value
    None clears that key rather than storing a null, so a caller can
    un-set a field without knowing its current value."""
    node = await node_repo.get(node_id)
    if node is None:
        raise ValueError(f"business node {node_id} not found")
    if node.layer is not Layer.BUSINESS:
        raise ValueError(f"node {node_id} is not a BUSINESS node")

    merged_attributes = {**node.attributes, **(attributes or {})}
    merged_attributes = {k: v for k, v in merged_attributes.items() if v is not None}

    updated = node.model_copy(
        update={
            "name": name if name is not None else node.name,
            "description": description if description is not None else node.description,
            "kind": kind if kind is not None else node.kind,
            "owners": owners if owners is not None else node.owners,
            "attributes": merged_attributes,
            "updated_at": datetime.now(UTC),
        }
    )
    return await node_repo.update(updated)


async def delete_business_node(
    node_repo: NodeRepository,
    context_space_repo: ContextSpaceRepository,
    node_id: UUID,
) -> None:
    """Soft-deletes one BUSINESS node — blocked (not cascaded) if
    anything still depends on it, so deleting a squad can never silently
    orphan its sub-teams or detach a context space from its anchor.
    A no-op, not an error, if the node is already gone."""
    node = await node_repo.get(node_id)
    if node is None:
        return

    children = await node_repo.list_direct_children(node_id)
    if children:
        names = ", ".join(c.name for c in children)
        raise BusinessNodeHasDependents(
            f"cannot delete {node.name!r}: {len(children)} child node(s) depend on it "
            f"({names}) — delete or move them first"
        )

    spaces = await context_space_repo.list_all()
    anchored = [s for s in spaces if s.business_node_id == node_id]
    if anchored:
        ids = ", ".join(s.id for s in anchored)
        raise BusinessNodeHasDependents(
            f"cannot delete {node.name!r}: context space(s) anchored to it ({ids}) — "
            "delete them first"
        )

    await node_repo.soft_delete(node_id, datetime.now(UTC))
