"""Azure DevOps connector.

Native hierarchy: Project -> Area Path -> Epic -> Feature -> Story/Task/Bug.
Also surfaces: Pull Requests, Builds, Releases, Wiki pages.

Maps ADO work items, area paths, PRs, and builds into domain/ Node and Edge
shapes. `mapper.py` is the only module here allowed to know ADO REST API
response shapes. Fixture data lives in fixtures/azure_devops/.

First connector implemented (docs/phases/PHASE-04.md) — it is the reference
implementation every later connector (github/, and any future connector) is
expected to follow.
"""

from __future__ import annotations

from context_fabric.connectors.azure_devops.fixture import AzureDevOpsFixtureConnector
from context_fabric.connectors.azure_devops.live import AzureDevOpsLiveConnector
from context_fabric.connectors.registry import register_fixture_connector, register_live_connector

register_fixture_connector("azure_devops", AzureDevOpsFixtureConnector)
register_live_connector("azure_devops", AzureDevOpsLiveConnector)

__all__ = ["AzureDevOpsFixtureConnector", "AzureDevOpsLiveConnector"]
