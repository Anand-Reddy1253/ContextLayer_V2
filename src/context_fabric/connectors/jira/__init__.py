"""Jira connector.

Native hierarchy: Project -> Issue -> child Issue (sub-tasks / epic
children), with Comments as leaves parented by the issue they belong to.

Maps Jira projects, issues, and comments into domain/ Node and Edge
shapes. `mapper.py` is the only module here allowed to know Jira's REST
API v3 response shapes. Fixture data lives in fixtures/jira/.
"""

from __future__ import annotations

from context_fabric.connectors.jira.fixture import JiraFixtureConnector
from context_fabric.connectors.jira.live import JiraLiveConnector
from context_fabric.connectors.registry import register_fixture_connector, register_live_connector

register_fixture_connector("jira", JiraFixtureConnector)
register_live_connector("jira", JiraLiveConnector)

__all__ = ["JiraFixtureConnector", "JiraLiveConnector"]
