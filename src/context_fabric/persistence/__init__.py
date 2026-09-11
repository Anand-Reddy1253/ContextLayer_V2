"""Persistence.

SQLAlchemy 2.x async ORM models (orm/) mirroring docs/persistence.md, an
async session/engine factory (session.py), and repository classes
(repositories/) — the only objects in this codebase allowed to hold a
SQLAlchemy Session or write raw SQL. Everything above this layer talks to
repositories, never to the ORM or the database directly.

Depends only on domain/.
"""

from __future__ import annotations
