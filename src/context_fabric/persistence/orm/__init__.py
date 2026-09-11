"""SQLAlchemy 2.x ORM mapped classes.

One module per table (or tightly-coupled table pair, mirroring how
domain/ groups them: context_space.py holds ContextSpace+Binding, sync.py
holds SyncState+SyncRun), matching docs/persistence.md column-for-column.

Physical schema (tables, indexes, constraints, CHECK clauses) is owned by
migrations/ — these mapped classes are the ORM's query-building view of
that schema, not the source of truth for DDL. If a mapped class and
docs/persistence.md diverge, docs/persistence.md is authoritative; fix the
mapped class.
"""

from __future__ import annotations

from context_fabric.persistence.orm.base import Base
from context_fabric.persistence.orm.checkpoint import TaskCheckpointORM
from context_fabric.persistence.orm.connector_connection import ConnectorConnectionORM
from context_fabric.persistence.orm.context_space import BindingORM, ContextSpaceORM
from context_fabric.persistence.orm.edge import EdgeORM
from context_fabric.persistence.orm.evidence import EvidenceORM
from context_fabric.persistence.orm.node import NodeORM
from context_fabric.persistence.orm.sync import SyncRunORM, SyncStateORM

__all__ = [
    "Base",
    "BindingORM",
    "ConnectorConnectionORM",
    "ContextSpaceORM",
    "EdgeORM",
    "EvidenceORM",
    "NodeORM",
    "SyncRunORM",
    "SyncStateORM",
    "TaskCheckpointORM",
]
