"""Page Properties macro parsing + template classification
(docs/CONNECTORS.md). The Page Properties macro
(`ac:structured-macro ac:name="details"`) renders a two-column table where
Confluence's own template enforces the left column as a fixed set of keys
— parsing that table directly gives typed key-values (`adr_status`,
`target_release`, `severity_level`) for free, consistently, without an LLM
call, because the template (not inference) enforced the shape.

Confluence records no `template_id` after page creation — what persists is
the blueprint label a human or the template itself attached. Classification
order is therefore labels -> page-properties keys -> title regex ->
unclassified — deliberately *not* -> LLM fallback, since semantic
classification is a separate, deferred tier (docs/adr's narrow-exception
precedent, ADR-010, hasn't been extended to this yet).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any
from xml.etree.ElementTree import Element

import yaml

from context_fabric.connectors.confluence.storage_format import AC_NS, local_name, qualified_tag

_CONFIGS_DIR = Path(__file__).resolve().parents[4] / "configs"


def _snake_case(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.strip().lower()).strip("_")


def extract_page_properties(root: Element) -> dict[str, str]:
    """Walks an already-parsed body tree (storage_format.parse_xml's
    result) for the Page Properties macro's table — first column is the
    key, second is the value, both taken as their concatenated visible
    text. Returns {} if the page has no such macro. Multiple details
    macros on one page (rare) merge, later rows winning on key collision."""
    properties: dict[str, str] = {}
    for macro in root.iter(qualified_tag(AC_NS, "structured-macro")):
        if macro.get(qualified_tag(AC_NS, "name")) != "details":
            continue
        for row in macro.iter("tr"):
            cells = [c for c in row if local_name(c.tag) in ("th", "td")]
            if len(cells) < 2:
                continue
            key = _snake_case("".join(cells[0].itertext()))
            value = "".join(cells[1].itertext()).strip()
            if key:
                properties[key] = value
    return properties


@dataclass(frozen=True)
class ConfluenceTemplate:
    name: str
    labels: list[str]
    page_properties_keys: list[str]
    title_pattern: str | None
    expected_keys: list[str]


@lru_cache(maxsize=1)
def _load_templates(path: Path | None = None) -> list[ConfluenceTemplate]:
    """Loaded once per process (this file never changes mid-run) — same
    lazy-cache convention synchronization/link_extraction.py's
    _relationship_rules() already uses for configs/relationships.yaml."""
    target = path or (_CONFIGS_DIR / "confluence-templates.yaml")
    raw = yaml.safe_load(target.read_text(encoding="utf-8"))
    return [
        ConfluenceTemplate(
            name=t["name"],
            labels=[label_.lower() for label_ in t.get("labels", [])],
            page_properties_keys=t.get("page_properties_keys", []),
            title_pattern=t.get("title_pattern"),
            expected_keys=t.get("expected_keys", []),
        )
        for t in raw["templates"]
    ]


@dataclass(frozen=True)
class PageClassification:
    page_type: str | None
    schema_completeness: float | None


def classify_page(
    *, title: str, labels: list[str], page_properties: dict[str, str]
) -> PageClassification:
    """labels -> page-properties keys -> title regex -> unclassified, in
    that order — the first matching template wins (configs/
    confluence-templates.yaml's own declared order breaks ties among
    templates matching on the same tier). schema_completeness is None for
    an unclassified page (there's no template's expected_keys to measure
    against), not 0.0 — 0.0 would wrongly read as "classified, but empty"."""
    lower_labels = {label_.lower() for label_ in labels}
    templates = _load_templates()

    matched: ConfluenceTemplate | None = None
    for template in templates:
        if lower_labels & set(template.labels):
            matched = template
            break
    if matched is None:
        for template in templates:
            if any(key in page_properties for key in template.page_properties_keys):
                matched = template
                break
    if matched is None:
        for template in templates:
            if template.title_pattern and re.search(template.title_pattern, title):
                matched = template
                break

    if matched is None:
        return PageClassification(page_type=None, schema_completeness=None)

    if not matched.expected_keys:
        return PageClassification(page_type=matched.name, schema_completeness=None)
    present = sum(1 for key in matched.expected_keys if key in page_properties)
    return PageClassification(
        page_type=matched.name, schema_completeness=present / len(matched.expected_keys)
    )


def page_type_attributes(
    classification: PageClassification, page_properties: dict[str, str]
) -> dict[str, Any]:
    """The attributes.* shape mapper.map_page merges in — a plain dict so
    the mapper doesn't need to know about PageClassification's own type."""
    return {
        "page_type": classification.page_type,
        "page_properties": page_properties,
        "schema_completeness": classification.schema_completeness,
    }
