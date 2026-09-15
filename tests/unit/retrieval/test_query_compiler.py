"""Query compiler — pure, so every operator is testable without Postgres.

Assertions are made against the compiled SQL string rather than by executing
it: the point here is that each operator produces the *intended* predicate
(and that user input never lands in SQL as text). Behaviour against real rows
is covered by the golden question set in tests/golden/.
"""

from __future__ import annotations

import pytest
from sqlalchemy.dialects import postgresql

from context_fabric.domain.query import PropertyRule, RelationRule, RuleGroup
from context_fabric.retrieval.query_compiler import QueryError, compile_group


def sql(group: RuleGroup, relations: dict | None = None) -> str:
    compiled = compile_group(group, relations or {})
    return str(compiled.compile(dialect=postgresql.dialect()))


def group(*rules, combinator: str = "and") -> RuleGroup:
    return RuleGroup.model_validate({"combinator": combinator, "rules": list(rules)})


# -- property resolution ----------------------------------------------------


def test_meta_property_resolves_to_a_real_column() -> None:
    out = sql(group({"property": "$blueprint", "operator": "=", "value": "STORY"}))
    assert "node.kind" in out
    assert "attributes" not in out


def test_bare_property_resolves_to_a_jsonb_attribute() -> None:
    out = sql(group({"property": "state", "operator": "=", "value": "Done"}))
    assert "attributes" in out


def test_vendor_and_sync_timestamps_are_different_properties() -> None:
    """$updatedAt is the vendor's; $syncedAt is ours. Conflating them would
    let "what changed recently?" be answered with our cron schedule."""
    assert "attributes" in sql(group({"property": "$updatedAt", "operator": ">", "value": "x"}))
    assert "last_seen_at" in sql(group({"property": "$syncedAt", "operator": ">", "value": "x"}))


def test_unknown_meta_property_is_rejected() -> None:
    with pytest.raises(QueryError, match="unknown meta-property"):
        sql(group({"property": "$nope", "operator": "=", "value": 1}))


# -- operators --------------------------------------------------------------


@pytest.mark.parametrize(
    ("operator", "expected"),
    [
        ("=", "="),
        (">", ">"),
        (">=", ">="),
        ("<", "<"),
        ("<=", "<="),
    ],
)
def test_comparison_operators(operator: str, expected: str) -> None:
    assert expected in sql(group({"property": "priority", "operator": operator, "value": 1}))


def test_not_equal_also_matches_rows_missing_the_attribute() -> None:
    """`state != Done` must include work items with no state at all —
    SQL's NULL != x is NULL, which would silently drop them."""
    out = sql(group({"property": "state", "operator": "!=", "value": "Done"}))
    assert "IS NULL" in out
    assert "OR" in out


@pytest.mark.parametrize("operator", ["contains", "beginsWith", "endsWith"])
def test_string_operators_use_ilike(operator: str) -> None:
    assert "ILIKE" in sql(group({"property": "$title", "operator": operator, "value": "auth"}))


def test_like_wildcards_in_input_are_escaped() -> None:
    """A literal % in a search term must not become a wildcard."""
    compiled = compile_group(
        group({"property": "$title", "operator": "contains", "value": "100%_done"}), {}
    )
    params = compiled.compile(dialect=postgresql.dialect()).params
    assert any("100\\%\\_done" in str(v) for v in params.values())


def test_in_and_not_in() -> None:
    assert "IN" in sql(group({"property": "state", "operator": "in", "value": ["A", "B"]}))
    assert "NOT" in sql(group({"property": "state", "operator": "notIn", "value": ["A"]}))


def test_list_operator_rejects_scalar_value() -> None:
    with pytest.raises(QueryError, match="requires a list"):
        sql(group({"property": "state", "operator": "in", "value": "A"}))


def test_between_requires_a_pair() -> None:
    assert ">=" in sql(group({"property": "priority", "operator": "between", "value": [1, 3]}))
    with pytest.raises(QueryError, match=r"\[low, high\]"):
        sql(group({"property": "priority", "operator": "between", "value": [1]}))


def test_is_empty_covers_missing_and_blank() -> None:
    out = sql(group({"property": "assigned_to", "operator": "isEmpty"}))
    assert "IS NULL" in out and "OR" in out
    assert "NOT" in sql(group({"property": "assigned_to", "operator": "isNotEmpty"}))


def test_valueless_operator_needs_no_value() -> None:
    PropertyRule.model_validate({"property": "x", "operator": "isEmpty"})


def test_operator_requiring_a_value_rejects_none() -> None:
    with pytest.raises(QueryError, match="requires a value"):
        sql(group({"property": "state", "operator": "=", "value": None}))


# -- structure --------------------------------------------------------------


def test_empty_group_matches_everything() -> None:
    assert "true" in sql(RuleGroup()).lower()


def test_and_versus_or() -> None:
    rules = [
        {"property": "state", "operator": "=", "value": "A"},
        {"property": "state", "operator": "=", "value": "B"},
    ]
    assert " AND " in sql(group(*rules, combinator="and"))
    assert " OR " in sql(group(*rules, combinator="or"))


def test_groups_nest() -> None:
    nested = group(
        {"property": "$blueprint", "operator": "=", "value": "STORY"},
        {
            "combinator": "or",
            "rules": [
                {"property": "priority", "operator": "=", "value": 1},
                {"property": "assigned_to", "operator": "isEmpty"},
            ],
        },
    )
    out = sql(nested)
    assert " AND " in out and " OR " in out


# -- relations --------------------------------------------------------------


def test_related_to_uses_the_preresolved_id_set() -> None:
    from uuid import uuid4

    rule = RelationRule(relation="VERIFIES", value="some-story")
    g = RuleGroup(rules=[rule])
    out = sql(g, {id(rule): {uuid4()}})
    assert "node.id IN" in out


def test_not_related_to_negates() -> None:
    from uuid import uuid4

    rule = RelationRule(relation="VERIFIES", value="s", operator="notRelatedTo")
    out = sql(RuleGroup(rules=[rule]), {id(rule): {uuid4()}})
    assert "NOT" in out


def test_unresolvable_relation_target_matches_nothing_for_relatedTo() -> None:
    """...and everything for notRelatedTo — "not related to something that
    doesn't exist" is vacuously true; silently returning the whole catalog
    would be the worse failure."""
    rel = RelationRule(relation="VERIFIES", value="ghost")
    assert "false" in sql(RuleGroup(rules=[rel]), {id(rel): set()}).lower()

    notrel = RelationRule(relation="VERIFIES", value="ghost", operator="notRelatedTo")
    assert "true" in sql(RuleGroup(rules=[notrel]), {id(notrel): set()}).lower()


def test_maxhops_is_bounded() -> None:
    with pytest.raises(ValueError):
        RelationRule(relation="CONTAINS", value="x", maxHops=99)
