"""Confluence connector.

Native hierarchy: Space -> Page -> child Page, with Attachments and
Comments as leaves parented by the page they belong to.

Maps Confluence spaces, pages, attachments, and comments into domain/
Node and Edge shapes. `mapper.py` is the only module here allowed to
know Confluence's REST API v2 response shapes. Fixture data lives in
fixtures/confluence/.

Added after the original scope's "do not implement full Confluence
connector" call was explicitly revisited and overridden by the user.
"""

from __future__ import annotations

from context_fabric.connectors.confluence.fixture import ConfluenceFixtureConnector
from context_fabric.connectors.confluence.live import ConfluenceLiveConnector
from context_fabric.connectors.registry import register_fixture_connector, register_live_connector

register_fixture_connector("confluence", ConfluenceFixtureConnector)
register_live_connector("confluence", ConfluenceLiveConnector)

__all__ = ["ConfluenceFixtureConnector", "ConfluenceLiveConnector"]
