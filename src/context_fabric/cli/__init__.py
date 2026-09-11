"""CLI.

Typer app (`context-fabric`, console script in pyproject.toml). Commands:

    context-fabric sync --source ado --fixture
    context-fabric sync --source github --fixture
    context-fabric reconcile --context-space talentflow/identity

Depends on synchronization/, connectors/, retrieval/. Implemented alongside
synchronization/ in Phase 6 (docs/phases/PHASE-06.md).
"""
