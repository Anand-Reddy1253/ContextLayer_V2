"""A `$blueprint` (kind) that doesn't exist at all, or doesn't exist for
the `$source` it's paired with, must not silently look like a real,
correct zero (found live: GitHub has no BUG kind — "bug" is only ever a
label on an ISSUE there — while Jira does have a real BUG kind; querying
`$blueprint=BUG, $source=github` returned a clean `matched: 0` with
nothing signaling the query's own premise was wrong). See
`api/routes/catalog.py`'s `blueprint_mismatch_warnings`.

native_id/source_instance_id values here are deliberately distinctive
(same convention as test_scope_resolution.py) since this shared dev
database also holds real data from live-connector smoke testing.
"""

from __future__ import annotations

from datetime import UTC, datetime

from context_fabric.api.routes.catalog import aggregate_entities, search_entities
from context_fabric.domain.query import AggregateQuery, EntityQuery, PropertyRule, RuleGroup
from context_fabric.persistence.repositories.node import NodeRepository
from tests.integration.persistence.factories import make_technical_node

_GITHUB_INSTANCE = "github-bmw-test"
_JIRA_INSTANCE = "jira-bmw-test"


async def _seed(node_repo, now):  # type: ignore[no-untyped-def]
    await node_repo.create(
        make_technical_node(
            now,
            kind="ISSUE",
            name="A GitHub issue",
            path="bmw_test.github_issue",
            source_system="github",
            source_instance_id=_GITHUB_INSTANCE,
            native_id="bmw-test/repo#1",
        )
    )
    await node_repo.create(
        make_technical_node(
            now,
            kind="BUG",
            name="A Jira bug",
            path="bmw_test.jira_bug",
            source_system="jira",
            source_instance_id=_JIRA_INSTANCE,
            native_id="BMW-1",
        )
    )


async def test_wrong_kind_for_source_gets_a_warning_not_a_bare_zero(db_session):
    await _seed(NodeRepository(db_session), datetime.now(UTC))

    query = RuleGroup(
        combinator="and",
        rules=[
            PropertyRule(property="$blueprint", operator="=", value="BUG"),
            PropertyRule(property="$source", operator="=", value="github"),
        ],
    )
    result = await search_entities(EntityQuery(query=query, limit=25), session=db_session)

    assert result["rollup"]["matched"] == 0
    assert "warnings" in result
    warning = result["warnings"][0]
    assert "BUG" in warning
    assert "github" in warning
    assert "jira" in warning  # tells the caller where BUG *does* exist


async def test_kind_that_exists_nowhere_gets_a_clear_warning(db_session):
    await _seed(NodeRepository(db_session), datetime.now(UTC))

    query = RuleGroup(
        rules=[PropertyRule(property="$blueprint", operator="=", value="NOT_A_REAL_KIND_BMW")]
    )
    result = await search_entities(EntityQuery(query=query, limit=25), session=db_session)

    assert result["rollup"]["matched"] == 0
    assert "warnings" in result
    assert "matches no node anywhere" in result["warnings"][0]


async def test_a_real_match_carries_no_warning(db_session):
    await _seed(NodeRepository(db_session), datetime.now(UTC))

    query = RuleGroup(
        rules=[PropertyRule(property="$blueprint", operator="=", value="ISSUE")]
    )
    result = await search_entities(EntityQuery(query=query, limit=25), session=db_session)

    assert result["rollup"]["matched"] >= 1
    assert "warnings" not in result


async def test_aggregate_entities_rest_route_is_unchanged_a_bare_list(db_session):
    """The REST route itself must keep returning a bare list — an
    existing golden-question test (test_golden_questions.py) already
    depends on this exact shape; the warnings behavior is layered on
    top only in mcp/tools.py's aggregate_entities_tool, not here."""
    await _seed(NodeRepository(db_session), datetime.now(UTC))
    query = RuleGroup(
        rules=[
            PropertyRule(property="$blueprint", operator="=", value="BUG"),
            PropertyRule(property="$source", operator="=", value="github"),
        ]
    )
    result = await aggregate_entities(
        AggregateQuery(query=query, group_by=["$source"]), session=db_session
    )
    assert result == []
