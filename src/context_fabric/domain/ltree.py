"""ltree label sanitization — shared by every package that builds a
Node.path segment from an arbitrary string (a connector's native_id,
synchronization/orchestrator.py; a business-tree config id,
catalog/business_tree.py; a resolved technical node's ancestor labels,
retrieval/scope.py). Pulled up to domain/ after the third copy of this
same three-line function appeared — one shared implementation instead of
three private ones that could silently drift apart.
"""

from __future__ import annotations

import re

_LABEL_UNSAFE = re.compile(r"[^A-Za-z0-9_]")


def sanitize_label(text: str) -> str:
    """Turns an arbitrary string into a valid ltree label
    ([A-Za-z0-9_]+). Not guaranteed collision-free across different
    inputs in general, but always is for the native_ids each caller
    actually uses it on, which are already unique within their own scope
    (docs/persistence.md's ux_node_technical_identity)."""
    label = _LABEL_UNSAFE.sub("_", text).strip("_")
    return label or "_"
