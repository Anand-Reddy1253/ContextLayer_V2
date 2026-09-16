"""Catalog.

The business layer (org structure: org -> division -> tribe -> squad ->
team, products, services) and the logical layer (ContextSpace + Binding —
the human-authored mapping from business scope to native connector
containers, docs/DOMAIN_MODEL.md).

Owns the write path the UI calls for business-tree CRUD and context-space
authoring (docs/UI.md, docs/API.md). Technical-layer nodes are never
writable through this package — those are sync-owned (synchronization/).

Depends on domain/, persistence/. Implemented starting Phase 8
(docs/phases/PHASE-08.md); single-node business-tree CRUD (as opposed to
bulk config seeding) was fast-tracked ahead of Phase 16 alongside the UI.
"""

from __future__ import annotations

from context_fabric.catalog.business_tree import (
    BusinessNodeHasDependents,
    business_path_to_ltree,
    create_business_node,
    delete_business_node,
    get_by_business_path,
    list_business_tree,
    load_business_tree_config,
    seed_business_tree,
    update_business_node,
)
from context_fabric.catalog.context_spaces import (
    BindingReconciliation,
    BusinessRefUnresolved,
    ReconcileReport,
    add_binding,
    create_context_space,
    create_context_space_from_fields,
    delete_context_space,
    find_context_space_config_by_id,
    get_context_space,
    list_context_spaces,
    load_context_space_config,
    reconcile_context_space,
    remove_binding,
    update_binding,
)
from context_fabric.catalog.workflow_templates import (
    AiAssetNotFound,
    NotAnAiAsset,
    add_step,
    create_workflow_template,
    delete_workflow_template,
    get_workflow_template,
    list_workflow_templates,
    remove_step,
    reorder_steps,
)

__all__ = [
    "AiAssetNotFound",
    "BindingReconciliation",
    "BusinessNodeHasDependents",
    "BusinessRefUnresolved",
    "NotAnAiAsset",
    "ReconcileReport",
    "add_binding",
    "add_step",
    "business_path_to_ltree",
    "create_business_node",
    "create_context_space",
    "create_context_space_from_fields",
    "create_workflow_template",
    "delete_business_node",
    "delete_context_space",
    "delete_workflow_template",
    "find_context_space_config_by_id",
    "get_by_business_path",
    "get_context_space",
    "get_workflow_template",
    "list_business_tree",
    "list_context_spaces",
    "list_workflow_templates",
    "load_business_tree_config",
    "load_context_space_config",
    "reconcile_context_space",
    "remove_binding",
    "remove_step",
    "reorder_steps",
    "seed_business_tree",
    "update_binding",
    "update_business_node",
]
