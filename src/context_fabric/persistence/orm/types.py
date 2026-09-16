"""Custom SQLAlchemy column types not built into sqlalchemy.dialects.postgresql.

LTree maps a Python str (dot-separated labels, e.g. "acme.eng.talentflow")
to Postgres's `ltree` column type. Binding a plain str works because the
ltree extension defines an IMPLICIT cast from text to ltree
(`CREATE CAST (text AS ltree) ... AS IMPLICIT`), so no explicit adapter
registration is needed for INSERT/UPDATE targets or comparisons.

On SQLite (no ltree extension) this compiles to plain TEXT instead — see
the `@compiles(LTree, "sqlite")` override below. The Python-side value is
already dialect-agnostic (a plain dot-separated string either way); only
the column DDL differs. Containment queries (`<@`) are a separate concern,
handled per call site in `persistence/dialect_compat.py` — this type only
controls what the column itself is declared as.
"""

from __future__ import annotations

from sqlalchemy.ext.compiler import compiles
from sqlalchemy.types import UserDefinedType


class LTree(UserDefinedType):
    cache_ok = True

    def get_col_spec(self, **kw: object) -> str:
        return "LTREE"

    def bind_processor(self, dialect):  # type: ignore[no-untyped-def]
        def process(value: str | None) -> str | None:
            return value

        return process

    def result_processor(self, dialect, coltype):  # type: ignore[no-untyped-def]
        def process(value: str | None) -> str | None:
            return value

        return process


@compiles(LTree, "sqlite")
def _compile_ltree_sqlite(element: LTree, compiler: object, **kw: object) -> str:
    return "TEXT"
