"""GitHub connector.

Native hierarchy: Organization -> Repository -> Branch -> Directory -> File.
Also surfaces: Pull Requests, Commits, GitHub Actions runs, GitHub Projects
items.

Maps GitHub REST/GraphQL responses into domain/ Node and Edge shapes.
`mapper.py` is the only module here allowed to know GitHub's payload shapes.
Fixture data lives in fixtures/github/.

Implemented in Phase 5 (docs/phases/PHASE-05.md), following the pattern set
by connectors/azure_devops/.
"""

from __future__ import annotations

from context_fabric.connectors.github.fixture import GitHubFixtureConnector
from context_fabric.connectors.github.live import GitHubLiveConnector
from context_fabric.connectors.registry import register_fixture_connector, register_live_connector

register_fixture_connector("github", GitHubFixtureConnector)
register_live_connector("github", GitHubLiveConnector)

__all__ = ["GitHubFixtureConnector", "GitHubLiveConnector"]
