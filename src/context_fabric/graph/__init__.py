"""Graph.

Traversal over the single node/edge table pair (docs/persistence.md):
recursive-CTE walks bounded by depth and edge-type filters
(traversal.py), and the ltree-based "everything under this path" queries
used by scope resolution.

No ranking or token-budget logic lives here — that is retrieval/. This
package answers "what is reachable"; retrieval/ answers "what matters most,
within budget."

Depends on domain/, persistence/. Implemented in Phase 7
(docs/phases/PHASE-07.md) for structural edges, extended as needed by later
phases.
"""

from __future__ import annotations

from context_fabric.graph.traversal import Direction, traverse

__all__ = ["Direction", "traverse"]
