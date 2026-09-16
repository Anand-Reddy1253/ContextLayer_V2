"""AI Explorer — shared, vendor-agnostic pieces for discovering agent/
skill/rule/command definitions a repo declares for a coding assistant
(`.github/agents/`, `.claude/skills/`, `.cursor/rules/`, etc.).

Originally built inline in `connectors/github/mapper.py` for GitHub only;
moved here once Azure DevOps needed the identical classification and
frontmatter-parsing logic — nothing about path classification or
frontmatter parsing is GitHub-specific, only the tree-fetch mechanics
(GitHub's git-trees API vs. ADO's Git Items API) differ, and those stay in
each connector's own `live.py`.

`native_id` shape ("{container}:ai-asset:{path}") is shared too — every
connector that has AI assets parents them under whatever its own
"repository" container's native_id already is (GitHub: "owner/repo", ADO: a
repo GUID), so the same marker-based encode/decode works for both without
either connector needing to know the other's container id shape.
"""

from __future__ import annotations

import hashlib
import re

import yaml

from context_fabric.domain.connector_types import SourceObject

AI_ASSET_PATH_RULES: list[tuple[str, str, str]] = [
    (".github/agents/", "github", "agent"),
    (".github/skills/", "github", "skill"),
    (".github/prompts/", "github", "prompt"),
    (".claude/agents/", "claude", "agent"),
    (".claude/skills/", "claude", "skill"),
    (".claude/commands/", "claude", "command"),
    (".cursor/rules/", "cursor", "rule"),
]

_FRONTMATTER_PATTERN = re.compile(r"^---\s*\n(.*?\n)---\s*\n", re.DOTALL)

_AI_ASSET_MARKER = ":ai-asset:"


def classify_ai_asset_path(path: str) -> tuple[str, str] | None:
    """Returns (vendor, asset_type) if `path` falls under a recognized
    AI-asset directory, else None — used to decide, from a repo's tree
    listing alone (no content fetch needed yet), which files are even
    worth fetching. Agent/skill/rule definitions are always markdown
    (`.md`) — a `.json` or other file sitting in the same directory
    (e.g. a `scope-map.json` config alongside real agent files) is
    support tooling, not a definition, and is excluded."""
    if not path.endswith(".md"):
        return None
    for prefix, vendor, asset_type in AI_ASSET_PATH_RULES:
        if path.startswith(prefix) and path != prefix:
            return vendor, asset_type
    return None


def parse_ai_asset_description(text: str, *, fallback_name: str) -> tuple[str, str]:
    """(name, description) from a skill/agent/rule file's own YAML
    frontmatter (`name:`/`description:`, the convention all three
    vendors use) when present; otherwise the first non-empty line of
    body text, truncated — a short excerpt only, never the full body
    (ADR-003: this is metadata for a catalog card, not a content
    replica)."""
    match = _FRONTMATTER_PATTERN.match(text)
    if match:
        try:
            data = yaml.safe_load(match.group(1)) or {}
        except yaml.YAMLError:
            data = {}
        if isinstance(data, dict):
            name = str(data.get("name") or fallback_name)
            description = str(data.get("description") or "")
            if description:
                return name, description[:300]
    for line in text.splitlines():
        stripped = line.strip().lstrip("#").strip()
        if stripped:
            return fallback_name, stripped[:300]
    return fallback_name, ""


def ai_asset_native_id(container_native_id: str, path: str) -> str:
    return f"{container_native_id}{_AI_ASSET_MARKER}{path}"


def parse_ai_asset_ref(native_id: str) -> tuple[str, str] | None:
    """(container_native_id, path) for an AI_ASSET native_id, else None.

    AI assets deliberately don't carry a branch/version in their native_id
    (they come from the repo's default branch), so they don't fit either
    connector's own "container@branch:path"-shaped parse_ref."""
    container, marker, path = native_id.partition(_AI_ASSET_MARKER)
    if not marker or not path:
        return None
    return container, path


def map_ai_asset(
    container_native_id: str,
    path: str,
    *,
    vendor: str,
    asset_type: str,
    name: str,
    description: str,
) -> SourceObject:
    return SourceObject(
        native_id=ai_asset_native_id(container_native_id, path),
        kind="AI_ASSET",
        name=name,
        parent_native_id=container_native_id,
        attributes={
            "vendor": vendor,
            "asset_type": asset_type,
            "path": path,
        },
        description=description or None,
        content_hash=hashlib.sha256(description.encode("utf-8")).hexdigest(),
    )
