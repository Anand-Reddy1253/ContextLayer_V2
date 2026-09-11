"""Repositories — the only objects allowed to hold a SQLAlchemy Session or
write SQL. Every method takes/returns context_fabric.domain types, never
an ORM object, to callers outside persistence/.
"""

from __future__ import annotations

from context_fabric.persistence.repositories.connector_connection import (
    ConnectorConnectionRepository,
    ConnectorConnectionSummary,
)
from context_fabric.persistence.repositories.context_space import ContextSpaceRepository
from context_fabric.persistence.repositories.edge import EdgeRepository
from context_fabric.persistence.repositories.evidence import EvidenceRepository
from context_fabric.persistence.repositories.node import NodeRepository
from context_fabric.persistence.repositories.sync_run import SyncRunRepository
from context_fabric.persistence.repositories.sync_state import SyncStateRepository
from context_fabric.persistence.repositories.task_checkpoint import TaskCheckpointRepository

__all__ = [
    "ConnectorConnectionRepository",
    "ConnectorConnectionSummary",
    "ContextSpaceRepository",
    "EdgeRepository",
    "EvidenceRepository",
    "NodeRepository",
    "SyncRunRepository",
    "SyncStateRepository",
    "TaskCheckpointRepository",
]
