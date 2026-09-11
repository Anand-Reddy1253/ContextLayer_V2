"""Microsoft Teams connector.

Native hierarchy: Channel -> Message -> Reply, all within one Team a
connection is scoped to.

Maps Teams channels, messages, and replies into domain/ Node and Edge
shapes — the COMMUNICATION capability's connector (configs/capabilities.yaml),
added at the user's explicit request: "what was actually discussed" in a
team's channel, not just a channel-name reference. `mapper.py` is the
only module here allowed to know Microsoft Graph's REST API response
shapes. Fixture data lives in fixtures/teams/.
"""

from __future__ import annotations

from context_fabric.connectors.registry import register_fixture_connector, register_live_connector
from context_fabric.connectors.teams.fixture import TeamsFixtureConnector
from context_fabric.connectors.teams.live import TeamsLiveConnector

register_fixture_connector("teams", TeamsFixtureConnector)
register_live_connector("teams", TeamsLiveConnector)

__all__ = ["TeamsFixtureConnector", "TeamsLiveConnector"]
