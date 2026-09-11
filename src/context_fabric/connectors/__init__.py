"""Connectors.

Vendor-facing integration layer. Every connector implements the
SourceConnector protocol (see base.py, and docs/CONNECTORS.md for the full
contract) in two modes:

  fixture mode — reads deterministic JSON fixtures from fixtures/<source>/,
                 no network calls, no credentials. Default and CI mode.
  live mode    — calls the real vendor API using credentials from
                 environment variables (.env.example), off by default.

Hard rule (enforced by an acceptance test, docs/CONNECTORS.md
"anti-leakage test"): no vendor-shaped dict, vendor SDK object, or raw API
response may cross out of a connector package. Every public method returns
domain/ types. Vendor-specific mapping lives in each connector's mapper.py
and is the only code allowed to know the vendor's payload shape.

Depends only on domain/. Implemented starting Phase 3
(docs/phases/PHASE-03.md).
"""

from __future__ import annotations

import context_fabric.connectors.azure_devops  # noqa: F401 (side effect: registers the connector)
import context_fabric.connectors.confluence  # noqa: F401 (side effect: registers the connector)
import context_fabric.connectors.github  # noqa: F401 (side effect: registers the connector)
import context_fabric.connectors.jira  # noqa: F401 (side effect: registers the connector)
import context_fabric.connectors.teams  # noqa: F401 (side effect: registers the connector)
from context_fabric.connectors.base import (
    FixtureConnectorBase,
    LiveConnectorBase,
    SourceConnector,
    correlate,
)
from context_fabric.connectors.registry import (
    get_fixture_connector_class,
    get_live_connector_class,
    register_fixture_connector,
    register_live_connector,
    registered_source_systems,
)

# Importing context_fabric.connectors always registers every known
# connector (see the imports above) — synchronization/ and cli/ never
# need to import a connector submodule directly to make it available via
# the registry.

__all__ = [
    "FixtureConnectorBase",
    "LiveConnectorBase",
    "SourceConnector",
    "correlate",
    "get_fixture_connector_class",
    "get_live_connector_class",
    "register_fixture_connector",
    "register_live_connector",
    "registered_source_systems",
]
