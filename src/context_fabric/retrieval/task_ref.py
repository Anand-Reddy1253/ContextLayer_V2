"""task_ref parsing (docs/RETRIEVAL.md §1, step 1) — a small per-source
pattern table mapping a task_ref string (e.g. "AB#312") to
(source_system, native_id), the first step of scope resolution.
Deliberately a flat table, not a parsing framework: a new source's
pattern is a one-line addition here, not a new abstraction.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# (pattern, source_system) — the first capture group becomes native_id.
_TASK_REF_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^AB#(\d+)$"), "azure_devops"),
]


@dataclass(frozen=True)
class ParsedTaskRef:
    task_ref: str
    source_system: str
    native_id: str


class UnrecognizedTaskRef(ValueError):
    """task_ref matched no known pattern — resolve_scope turns this into
    an explicit unresolved ScopeResolution rather than letting it
    propagate as a raw exception (docs/phases/PHASE-09.md "never a
    silent empty success")."""


def parse_task_ref(task_ref: str) -> ParsedTaskRef:
    for pattern, source_system in _TASK_REF_PATTERNS:
        match = pattern.match(task_ref)
        if match:
            return ParsedTaskRef(
                task_ref=task_ref, source_system=source_system, native_id=match.group(1)
            )
    raise UnrecognizedTaskRef(f"task_ref {task_ref!r} matches no known pattern")
