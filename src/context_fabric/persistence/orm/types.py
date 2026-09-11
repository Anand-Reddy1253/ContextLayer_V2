"""Custom SQLAlchemy column types not built into sqlalchemy.dialects.postgresql.

LTree maps a Python str (dot-separated labels, e.g. "acme.eng.talentflow")
to Postgres's `ltree` column type. Binding a plain str works because the
ltree extension defines an IMPLICIT cast from text to ltree
(`CREATE CAST (text AS ltree) ... AS IMPLICIT`), so no explicit adapter
registration is needed for INSERT/UPDATE targets or comparisons.
"""

from __future__ import annotations

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
