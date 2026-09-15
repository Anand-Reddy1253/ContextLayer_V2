"""The entity query grammar — a JSON rule tree an agent can construct.

Deliberately mirrors Port.io's search syntax (combinator + rules, `$`-prefixed
meta-properties, `relatedTo` for graph traversal), because an LLM that has seen
Port's format should be able to write a valid query here without relearning a
dialect. The shapes are ours; the vocabulary is theirs where it made sense.

Why a grammar at all: `GET /search` takes six scalar parameters and ANDs them.
There is no OR, no nesting, no operator beyond implicit equality, and no way to
filter by a relationship — so "stories that are not Done and have no test
coverage" is simply not expressible, and neither is anything an agent would
actually ask.

The tree is compiled to a SQLAlchemy predicate by
retrieval/query_compiler.py; nothing here touches a database or a session.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Combinator = Literal["and", "or"]

# Grouped the way a caller thinks about them, not the way SQL does. Kept as a
# flat Literal (rather than a StrEnum) so the JSON an agent writes is exactly
# the operator string, with no serialization layer in between.
Operator = Literal[
    # equality
    "=",
    "!=",
    # string
    "contains",
    "doesNotContain",
    "beginsWith",
    "endsWith",
    # array / set membership
    "in",
    "notIn",
    "containsAny",
    # numeric + date ordering
    ">",
    ">=",
    "<",
    "<=",
    "between",
    "notBetween",
    # existence
    "isEmpty",
    "isNotEmpty",
]

# Operators that take no `value` at all — validated rather than silently
# ignoring whatever was passed, so a malformed query fails loudly.
VALUELESS_OPERATORS: frozenset[str] = frozenset({"isEmpty", "isNotEmpty"})

# Operators whose `value` must be a two-element [low, high] range.
RANGE_OPERATORS: frozenset[str] = frozenset({"between", "notBetween"})

# Operators whose `value` must be a list.
LIST_OPERATORS: frozenset[str] = frozenset({"in", "notIn", "containsAny"})


class PropertyRule(BaseModel):
    """Filter on a field of the entity itself.

    `property` is either a `$`-prefixed meta-property mapping to a real column
    (see query_compiler.META_PROPERTIES) or a bare key read from the node's
    `attributes` JSONB. Meta-properties exist because the interesting fields
    live in two different places — `name`/`kind`/`native_id` are columns while
    `state`/`priority`/`assigned_to` are attributes — and a caller should not
    have to know which is which.
    """

    model_config = ConfigDict(extra="forbid")

    property: str
    operator: Operator
    value: Any = None


class RelationRule(BaseModel):
    """Filter by connection to another entity, via graph traversal.

    `relation` is an EdgeType value (CONTAINS, IMPLEMENTS, VERIFIES, ...).
    `value` is the node id or native_id at the far end.

    `notRelatedTo` has no Port equivalent and is ours: every "what's missing"
    question needs it — stories with no test coverage, repos with no owning
    team, work items with no linked PR. Those are the questions a catalog can
    answer that the source systems individually cannot.
    """

    model_config = ConfigDict(extra="forbid")

    relation: str
    operator: Literal["relatedTo", "notRelatedTo"] = "relatedTo"
    value: str | list[str]
    # Port's vocabulary. `downstream` = follow edges outward from the target
    # (things it points at); `upstream` = follow them inward (things pointing
    # at it). Mapped onto graph/traversal.py's "out"/"in"/"both".
    direction: Literal["upstream", "downstream", "both"] = "both"
    # Capped low on purpose: each hop multiplies the reachable set, and an
    # unbounded walk over a container-heavy graph reaches nearly everything
    # (measured: following all edge types from one team reached 469 of ~476
    # nodes). A caller wanting more should say so explicitly.
    maxHops: int = Field(default=1, ge=1, le=6)


class RuleGroup(BaseModel):
    """A combinator over rules, nestable to arbitrary depth."""

    model_config = ConfigDict(extra="forbid")

    combinator: Combinator = "and"
    rules: list[Rule] = Field(default_factory=list)


# Discriminating on field presence rather than a tag: a rule with `property` is
# a PropertyRule, one with `relation` is a RelationRule, one with `rules` is a
# nested group. That keeps the JSON an agent writes identical to Port's, which
# carries no explicit type tag either.
Rule = Annotated[
    PropertyRule | RelationRule | RuleGroup,
    Field(union_mode="left_to_right"),
]

RuleGroup.model_rebuild()


class EntityQuery(BaseModel):
    """A full search request."""

    model_config = ConfigDict(extra="forbid")

    query: RuleGroup = Field(default_factory=RuleGroup)
    limit: int = Field(default=25, ge=1, le=200)
    # Opaque keyset cursor; None starts from the beginning.
    cursor: str | None = None


MetricOp = Literal["count", "avg", "min", "max", "sum", "avg_duration_days"]


class MetricSpec(BaseModel):
    """One aggregated value in an AggregateQuery response.

    `count` needs nothing else. `avg`/`min`/`max`/`sum` need `property` — a
    numeric attribute (`priority`) or a timestamp one, compared as text, which
    works for min/max but not avg/sum. `avg_duration_days` is the metric that
    actually answers "PR cycle time" or "time to close" — the two-timestamp
    interval the plain aggregates can't express — computed as
    avg(`end` - `start`) in days, over rows where both are present.
    """

    model_config = ConfigDict(extra="forbid")

    op: MetricOp = "count"
    property: str | None = None
    start: str | None = None
    end: str | None = None
    # Output key in the response row; defaults to a name derived from the
    # metric itself (e.g. "avg_priority", "avg_duration_days") if not given.
    as_: str | None = Field(default=None, alias="as")


class AggregateQuery(BaseModel):
    """Group-and-count over the same filter grammar.

    Computed live in SQL rather than materialized at sync time — at the scale
    this runs, a GROUP BY is cheaper than the machinery to keep a precomputed
    value correct, and a stale aggregate is worse than a slow one.
    """

    model_config = ConfigDict(extra="forbid")

    query: RuleGroup = Field(default_factory=RuleGroup)
    # Property names, same vocabulary as PropertyRule.property.
    group_by: list[str] = Field(default_factory=list, max_length=3)
    metrics: list[MetricSpec] = Field(default_factory=lambda: [MetricSpec()])
