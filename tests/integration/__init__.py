"""Integration tests: real Postgres (docker compose up -d postgres),
fixture-mode connectors, real sync runs. Verify repository queries, graph
traversal SQL, migrations, and idempotent sync against an actual database.
No live vendor network calls.
"""
