"""Runs tests/golden/questions.yaml against the real database.

This is the acceptance gate for the entity query language. Each question is a
thing a person would ask, the query an agent should build for it, and an
assertion about the answer.

Questions marked `expect: blocked` are skipped rather than failed — they record
what the catalog *cannot* answer yet and why. That list shrinking is the real
measure of progress; a suite that only contains passing cases would hide it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from context_fabric.api.routes.catalog import aggregate_entities, search_entities
from context_fabric.domain.query import AggregateQuery, EntityQuery, RuleGroup

QUESTIONS_PATH = Path(__file__).resolve().parents[1] / "golden" / "questions.yaml"
QUESTIONS: list[dict[str, Any]] = yaml.safe_load(QUESTIONS_PATH.read_text(encoding="utf-8"))[
    "questions"
]

ANSWERABLE = [q for q in QUESTIONS if q.get("expect") != "blocked"]
BLOCKED = [q for q in QUESTIONS if q.get("expect") == "blocked"]


@pytest.mark.parametrize("question", ANSWERABLE, ids=lambda q: q["id"])
@pytest.mark.asyncio
async def test_golden_question(question: dict[str, Any], db_session) -> None:  # noqa: ANN001
    expect = question["expect"]

    if "aggregate" in question:
        spec = question["aggregate"]
        request = AggregateQuery(
            query=RuleGroup.model_validate(spec.get("query") or {}),
            group_by=spec["group_by"],
        )
        groups = await aggregate_entities(request, session=db_session)
        assert len(groups) >= expect["min_groups"], (
            f"{question['ask']!r} returned {len(groups)} groups, "
            f"expected at least {expect['min_groups']}"
        )
        # Every group must carry a count, or the aggregate is shaped wrong.
        assert all("count" in g for g in groups)
        return

    request = EntityQuery(query=RuleGroup.model_validate(question["query"]), limit=200)
    result = await search_entities(request, session=db_session)

    matched = result["rollup"]["matched"]
    assert matched >= expect["min_count"], (
        f"{question['ask']!r} matched {matched}, expected at least {expect['min_count']}"
    )

    if expect.get("kinds"):
        returned = set(result["rollup"]["by_kind"])
        assert returned <= set(expect["kinds"]), (
            f"{question['ask']!r} returned kinds {sorted(returned)}, "
            f"expected only {sorted(expect['kinds'])}"
        )

    # Shape contract every answer must honour, regardless of the question.
    assert set(result) >= {"rollup", "anchors", "nodes", "edges"}
    for anchor in result["anchors"]:
        assert anchor["ref"] in result["nodes"], "anchor references a node not in the dictionary"
    for edge in result["edges"]:
        assert edge["src"] in result["nodes"] and edge["dst"] in result["nodes"], (
            "edge references a node not in the dictionary"
        )


@pytest.mark.parametrize("question", BLOCKED, ids=lambda q: q["id"])
def test_known_gap(question: dict[str, Any]) -> None:
    """Not a failure — a recorded gap, with the reason it exists."""
    pytest.skip(f"{question['ask']} — {question['blocked_reason'].strip()}")
