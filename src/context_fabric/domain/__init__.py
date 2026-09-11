"""Domain models.

Pydantic models, enums, and error types for every entity described in
docs/DOMAIN_MODEL.md. Pure data + validation. No I/O beyond the explicit
config loaders in config.py, and no imports from any other context_fabric
subpackage — this is the one package every other package may depend on
(see src/context_fabric/__init__.py for the full dependency graph).
"""

from __future__ import annotations

from context_fabric.domain.checkpoint import TaskCheckpoint
from context_fabric.domain.config import (
    CapabilitiesConfig,
    CapabilityDefinition,
    StageContract,
    StageContractDefaults,
    StageContractsConfig,
    StageSlot,
    TraversalSpec,
    load_capabilities,
    load_stage_contracts,
)
from context_fabric.domain.connector_types import (
    ACLReference,
    ChangePage,
    Page,
    SourceContainer,
    SourceContent,
    SourceLink,
    SourceObject,
)
from context_fabric.domain.context_pack import (
    ContextPack,
    ContextPackItem,
    ExpansionHandle,
    FreshnessEntry,
)
from context_fabric.domain.context_space import Binding, ContextSpace
from context_fabric.domain.edge import Edge
from context_fabric.domain.enums import (
    Capability,
    EdgeOrigin,
    EdgeState,
    EdgeType,
    ErrorCategory,
    Layer,
    NodeStatus,
    SyncStatus,
)
from context_fabric.domain.errors import (
    AuthError,
    ConnectorError,
    NotFound,
    Permanent,
    RateLimited,
    SchemaDrift,
    Transient,
)
from context_fabric.domain.evidence import Evidence
from context_fabric.domain.ltree import sanitize_label
from context_fabric.domain.node import Node
from context_fabric.domain.sync import SyncRun, SyncState

__all__ = [
    "ACLReference",
    "AuthError",
    "Binding",
    "CapabilitiesConfig",
    "Capability",
    "CapabilityDefinition",
    "ChangePage",
    "ConnectorError",
    "ContextPack",
    "ContextPackItem",
    "ContextSpace",
    "Edge",
    "EdgeOrigin",
    "EdgeState",
    "EdgeType",
    "ErrorCategory",
    "Evidence",
    "ExpansionHandle",
    "FreshnessEntry",
    "Layer",
    "Node",
    "NodeStatus",
    "NotFound",
    "Page",
    "Permanent",
    "RateLimited",
    "SchemaDrift",
    "sanitize_label",
    "SourceContainer",
    "SourceContent",
    "SourceLink",
    "SourceObject",
    "StageContract",
    "StageContractDefaults",
    "StageContractsConfig",
    "StageSlot",
    "SyncRun",
    "SyncState",
    "SyncStatus",
    "TaskCheckpoint",
    "Transient",
    "TraversalSpec",
    "load_capabilities",
    "load_stage_contracts",
]
