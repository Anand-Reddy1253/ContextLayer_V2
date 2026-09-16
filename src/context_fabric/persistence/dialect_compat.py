"""The handful of query patterns that genuinely differ between Postgres and
SQLite — everything else in this project (JSON access via SQLAlchemy's
generic `JSON` type, `WITH RECURSIVE`, `.ilike()`) already compiles
correctly on both without a branch. This module exists so those branches
live in exactly one place each, not duplicated at every call site.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import ColumnElement, or_


def path_contains(col: Any, ancestor_path: str, dialect_name: str) -> ColumnElement[bool]:
    """`ancestor_path` itself, or anything under it — Postgres's `ltree`
    expresses this natively as `<@` (GiST-indexed, `ix_node_path_gist`,
    migration 0002). SQLite has no ltree; since a path is always just
    dot-separated labels, prefix-LIKE is exactly equivalent (`path = X` or
    `path LIKE 'X.%'`) and needs no index beyond the ordinary one on the
    column."""
    if dialect_name == "sqlite":
        return or_(col == ancestor_path, col.like(f"{ancestor_path}.%"))
    return col.op("<@")(ancestor_path)
