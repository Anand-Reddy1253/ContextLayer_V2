"""Synchronization.

Orchestrates connectors -> domain models -> persistence: discover
containers, paginate list_children, upsert nodes idempotently keyed on
(source_system, source_instance_id, native_id), diff via content_hash,
create structural CONTAINS edges, extract and resolve links (get_links) into
MENTIONS/RELATED_TO edges, and honor deletes/tombstones from get_changes.

Maintains SyncState and SyncRun (persistence/). The idempotency contract —
running the same fixture sync twice produces zero net graph change — is
enforced and tested here (docs/phases/PHASE-06.md acceptance gate).

Depends on domain/, persistence/, connectors/, graph/. Implemented in
Phase 6 (docs/phases/PHASE-06.md) with hierarchy/relationship extraction
detailed further in Phase 7 (docs/phases/PHASE-07.md).
"""

from __future__ import annotations

from context_fabric.synchronization.orchestrator import SyncStats, sync_source

__all__ = ["SyncStats", "sync_source"]
