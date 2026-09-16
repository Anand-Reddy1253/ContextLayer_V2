"""task_ref parsing (docs/RETRIEVAL.md §1, step 1) — a small per-source
pattern table mapping a task_ref string (e.g. "AB#312") to
(source_system, native_id), the first step of scope resolution.
Deliberately a flat table, not a parsing framework: a new source's
pattern is a one-line addition here, not a new abstraction.

The canonical shapes reuse the same regexes `connectors/cross_references.py`
already defines for finding these references embedded in text (a reference
shape should be defined once) — anchored here with fullmatch since a
task_ref is the whole string, not a substring to extract from a body. Only
the shapes whose native_id needs no other context to resolve are reused
(e.g. not `github_same_repo_key`'s "#7", which needs a repo to qualify it).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from re import Match

# (pattern, source_system, native_id builder) — native_id shape differs by
# source (see each mapper's own native_id convention: ADO work items use the
# bare number, GitHub issues/PRs use "owner/repo#number", Confluence pages
# use the bare page id, Jira issues use the full key), so this needs a
# builder rather than always taking group(1). Order matters only where two
# shapes can match the same string: the Jira key pattern is last so it never
# shadows the more specific ADO/GitHub/Confluence shapes, same ordering
# discipline as REFERENCE_PATTERNS in cross_references.py.
_TASK_REF_PATTERNS: list[tuple[re.Pattern[str], str, Callable[[Match[str]], str]]] = [
    (re.compile(r"^AB#(\d+)$"), "azure_devops", lambda m: m.group(1)),
    (
        re.compile(r"^([\w.-]+/[\w.-]+)#(\d+)$"),
        "github",
        lambda m: f"{m.group(1)}#{m.group(2)}",
    ),
    (re.compile(r"^CONFPAGE-(\d+)$"), "confluence", lambda m: m.group(1)),
    (re.compile(r"^([A-Z][A-Z0-9]{1,9}-\d+)$"), "jira", lambda m: m.group(1)),
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
    for pattern, source_system, build_native_id in _TASK_REF_PATTERNS:
        match = pattern.match(task_ref)
        if match:
            return ParsedTaskRef(
                task_ref=task_ref,
                source_system=source_system,
                native_id=build_native_id(match),
            )
    raise UnrecognizedTaskRef(f"task_ref {task_ref!r} matches no known pattern")
