"""Compiles a domain/query.py rule tree into a SQLAlchemy predicate.

Two properties worth keeping as this grows:

* **Pure.** `compile_group` takes no session and touches no database, so every
  operator is unit-testable without Postgres. Relation rules are the exception
  and are resolved to id sets *before* compilation (see `resolve_relations`),
  which keeps the compiler itself synchronous and side-effect free.
* **Whitelisted.** A property name never reaches SQL as text. Meta-properties
  map to real columns through META_PROPERTIES; anything else becomes a
  parameterized JSONB key lookup. There is no path by which a caller-supplied
  string is interpolated into a statement.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import (
    TIMESTAMP,
    ColumnElement,
    Numeric,
    Text,
    and_,
    cast,
    false,
    func,
    not_,
    or_,
    true,
)
from sqlalchemy.ext.asyncio import AsyncSession

from context_fabric.domain.enums import EdgeType
from context_fabric.domain.query import (
    LIST_OPERATORS,
    RANGE_OPERATORS,
    VALUELESS_OPERATORS,
    MetricSpec,
    PropertyRule,
    RelationRule,
    RuleGroup,
)
from context_fabric.graph.traversal import traverse
from context_fabric.persistence.dialect_compat import path_contains
from context_fabric.persistence.orm.node import NodeORM


class QueryError(ValueError):
    """A malformed query — surfaced to the caller as a 400, never a 500.

    An agent writing queries will get them wrong; the message is the only
    feedback it has, so it names the offending value and what was expected.
    """


# The `$`-prefixed vocabulary, mapping to real columns. Everything not listed
# here is read from the `attributes` JSONB.
#
# `$updatedAt` is deliberately the *vendor's* timestamp (an attribute), while
# our own sync time is exposed separately as `$syncedAt`. Conflating them would
# let "what changed this week?" be answered with our cron schedule — and since
# sync touches every node on every run, that answer would be confidently,
# uselessly wrong.
META_PROPERTIES: dict[str, Any] = {
    "$identifier": NodeORM.native_id,
    "$title": NodeORM.name,
    "$blueprint": NodeORM.kind,
    "$kind": NodeORM.kind,
    "$source": NodeORM.source_system,
    "$layer": NodeORM.layer,
    "$path": NodeORM.path,
    "$description": NodeORM.description,
    "$syncedAt": NodeORM.last_seen_at,
}

# Vendor timestamps live in attributes but deserve first-class names.
META_ATTRIBUTE_ALIASES: dict[str, str] = {
    "$createdAt": "created_at",
    "$updatedAt": "updated_at",
}


def _column_for(property_name: str) -> Any:
    """Resolve a query property to something comparable."""
    if property_name in META_PROPERTIES:
        return META_PROPERTIES[property_name]
    key = META_ATTRIBUTE_ALIASES.get(property_name, property_name)
    if key.startswith("$"):
        raise QueryError(
            f"unknown meta-property {property_name!r}; "
            f"known: {', '.join(sorted(META_PROPERTIES) + sorted(META_ATTRIBUTE_ALIASES))}"
        )
    # `.as_string()` renders as `attributes ->> :key` on Postgres /
    # `JSON_EXTRACT(attributes, :key)` on SQLite, with the key bound, not
    # inlined either way — a property name can never become SQL. (Not
    # `.astext`: that's Postgres-JSONB-only; `.as_string()` is
    # SQLAlchemy's generic, dialect-portable equivalent — verified to
    # compile correctly on both.)
    return NodeORM.attributes[key].as_string()


def _escape_like(value: str) -> str:
    """LIKE wildcards in user input are literal characters, not operators."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _compile_property(rule: PropertyRule, dialect_name: str) -> ColumnElement[bool]:
    col = _column_for(rule.property)
    op = rule.operator
    value = rule.value

    # `path` is an ltree (Postgres) or plain text (SQLite — see
    # persistence/orm/types.py's LTree), not something string operators are
    # the right tool for either way. "beginsWith" on a path means
    # "descendant of", which ltree expresses natively as `<@`
    # (`ix_node_path_gist`-indexed) and SQLite as a prefix LIKE — see
    # persistence/dialect_compat.py, the same helper
    # NodeRepository.list_descendants uses. Remaining string operators fall
    # back to a text cast so they at least behave predictably.
    if rule.property == "$path":
        if op == "beginsWith":
            return path_contains(col, str(value), dialect_name)
        if op == "=":
            return col == str(value)
        if op in ("contains", "endsWith", "doesNotContain"):
            col = cast(col, Text)

    if op in VALUELESS_OPERATORS:
        # "empty" covers both a missing key and an explicit blank — for a
        # JSONB attribute those are different states but mean the same thing
        # to anyone asking "which work items have no assignee?".
        empty = or_(col.is_(None), col == "")
        return empty if op == "isEmpty" else not_(empty)

    if value is None:
        raise QueryError(f"operator {op!r} requires a value")

    if op in LIST_OPERATORS:
        if not isinstance(value, list):
            raise QueryError(f"operator {op!r} requires a list value, got {type(value).__name__}")
        if op == "in":
            return col.in_(value)
        if op == "notIn":
            return col.notin_(value)
        # containsAny: the attribute holds a JSON array (labels, tags) and we
        # ask whether any requested element is present. Compared as text so it
        # works uniformly whether the array was stored as JSON or a scalar.
        key = META_ATTRIBUTE_ALIASES.get(rule.property, rule.property)
        if rule.property in META_PROPERTIES:
            raise QueryError(f"containsAny is not supported on {rule.property!r}")
        return or_(*[NodeORM.attributes[key].as_string().contains(str(v)) for v in value])

    if op in RANGE_OPERATORS:
        if not isinstance(value, list) or len(value) != 2:
            raise QueryError(f"operator {op!r} requires a [low, high] value")
        low, high = value
        between = and_(col >= low, col <= high)
        return between if op == "between" else not_(between)

    if op == "=":
        return col == value
    if op == "!=":
        # NULL != x is NULL in SQL, so a node missing the attribute would be
        # silently dropped — almost never what "is not Done" is meant to mean.
        return or_(col.is_(None), col != value)
    if op == "contains":
        return col.ilike(f"%{_escape_like(str(value))}%", escape="\\")
    if op == "doesNotContain":
        return or_(col.is_(None), not_(col.ilike(f"%{_escape_like(str(value))}%", escape="\\")))
    if op == "beginsWith":
        return col.ilike(f"{_escape_like(str(value))}%", escape="\\")
    if op == "endsWith":
        return col.ilike(f"%{_escape_like(str(value))}", escape="\\")
    if op in (">", ">=", "<", "<="):
        return {
            ">": col > value,
            ">=": col >= value,
            "<": col < value,
            "<=": col <= value,
        }[op]

    raise QueryError(f"unsupported operator {op!r}")


_DIRECTION_MAP = {"downstream": "out", "upstream": "in", "both": "both"}


async def resolve_relations(
    session: AsyncSession, group: RuleGroup, _resolved: dict[int, set[UUID]] | None = None
) -> dict[int, set[UUID]]:
    """Pre-resolve every RelationRule in the tree to a set of node ids.

    Done ahead of compilation, keyed by `id()` of the rule object, so the
    compiler stays synchronous and pure. Reuses graph/traversal.py's recursive
    CTE — which already does exactly what Port's `relatedTo` describes
    (edge-type filter, hop limit, direction) and which nothing in the codebase
    called until now.
    """
    resolved = _resolved if _resolved is not None else {}
    for rule in group.rules:
        if isinstance(rule, RuleGroup):
            await resolve_relations(session, rule, resolved)
        elif isinstance(rule, RelationRule):
            try:
                edge_type = EdgeType(rule.relation)
            except ValueError as exc:
                raise QueryError(
                    f"unknown relation {rule.relation!r}; "
                    f"known: {', '.join(sorted(e.value for e in EdgeType))}"
                ) from exc
            targets = rule.value if isinstance(rule.value, list) else [rule.value]
            found: set[UUID] = set()
            for target in targets:
                root = await _resolve_node_id(session, target)
                if root is None:
                    continue
                nodes = await traverse(
                    session,
                    root,
                    edge_types=[edge_type],
                    max_hops=rule.maxHops,
                    direction=_DIRECTION_MAP[rule.direction],  # type: ignore[arg-type]
                )
                found.update(n.id for n in nodes)
            resolved[id(rule)] = found
    return resolved


async def _resolve_node_id(session: AsyncSession, value: str) -> UUID | None:
    """Accept either a node UUID or a vendor native_id as the relation target —
    an agent constructing a query has seen native_ids in results far more often
    than it has seen our internal UUIDs."""
    from sqlalchemy import select

    try:
        return UUID(value)
    except ValueError:
        pass
    stmt = select(NodeORM.id).where(
        NodeORM.native_id == value, NodeORM.deleted_at.is_(None)
    )
    return (await session.execute(stmt)).scalars().first()


def compile_group(
    group: RuleGroup, relations: dict[int, set[UUID]], dialect_name: str = "postgresql"
) -> ColumnElement[bool]:
    """The rule tree as one SQLAlchemy boolean expression.

    `dialect_name` only matters for `$path beginsWith` (see
    `persistence/dialect_compat.py`) — everything else here already
    compiles identically on Postgres and SQLite. Defaults to
    `"postgresql"` so existing callers/tests that don't pass it keep
    today's behavior unchanged; still a pure function — a dialect name is
    a string, not a session, so this doesn't touch a database."""
    if not group.rules:
        return true()

    clauses: list[ColumnElement[bool]] = []
    for rule in group.rules:
        if isinstance(rule, RuleGroup):
            clauses.append(compile_group(rule, relations, dialect_name))
        elif isinstance(rule, RelationRule):
            ids = relations.get(id(rule), set())
            if not ids:
                # An unresolvable target matches nothing for relatedTo, and
                # everything for notRelatedTo — "not related to a thing that
                # doesn't exist" is vacuously true, and silently returning the
                # whole catalog instead would be worse.
                clauses.append(false() if rule.operator == "relatedTo" else true())
            else:
                in_set = NodeORM.id.in_(ids)
                clauses.append(in_set if rule.operator == "relatedTo" else not_(in_set))
        else:
            clauses.append(_compile_property(rule, dialect_name))

    return and_(*clauses) if group.combinator == "and" else or_(*clauses)


def compile_metrics(metrics: list[MetricSpec]) -> list[tuple[str, ColumnElement[Any]]]:
    """(output_key, SQLAlchemy expression) per requested metric.

    `avg`/`sum` cast to Numeric — correct for a numeric attribute
    (`priority`) and the reason those two ops, specifically, need one:
    Postgres has no SUM/AVG over text. `min`/`max` compare the raw text
    column, which is correct both for numeric strings and for ISO 8601
    timestamps (lexicographic order matches chronological order for that
    format), so no cast is needed there.

    `avg_duration_days` is the metric that actually answers "PR cycle
    time" — a plain `avg` can't express a computed interval between two
    properties, which `count`/`avg`/`min`/`max`/`sum` alone never could.
    NULLs (a row missing `start` or `end`) are excluded from the average by
    Postgres's own AVG, not filtered here.
    """
    out: list[tuple[str, ColumnElement[Any]]] = []
    for spec in metrics:
        if spec.op == "count":
            out.append((spec.as_ or "count", func.count()))
            continue

        if spec.op == "avg_duration_days":
            if not spec.start or not spec.end:
                raise QueryError("avg_duration_days requires both 'start' and 'end'")
            start_ts = cast(_column_for(spec.start), TIMESTAMP)
            end_ts = cast(_column_for(spec.end), TIMESTAMP)
            seconds = func.extract("epoch", end_ts - start_ts)
            out.append((spec.as_ or "avg_duration_days", func.avg(seconds / 86400.0)))
            continue

        if spec.property is None:
            raise QueryError(f"metric op {spec.op!r} requires 'property'")
        col = _column_for(spec.property)
        default_key = f"{spec.op}_{spec.property.lstrip('$')}"
        key = spec.as_ or default_key
        if spec.op in ("avg", "sum"):
            numeric_col = cast(col, Numeric)
            fn = func.avg if spec.op == "avg" else func.sum
            out.append((key, fn(numeric_col)))
        elif spec.op == "min":
            out.append((key, func.min(col)))
        elif spec.op == "max":
            out.append((key, func.max(col)))
        else:
            raise QueryError(f"unsupported metric op {spec.op!r}")
    return out
