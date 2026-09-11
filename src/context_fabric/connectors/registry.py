"""Connector registry — the one place `source_system` strings map to
connector classes. `synchronization/` and `cli/` resolve connectors
through this registry, never by importing a connector class directly, so
adding a connector (docs/CONNECTORS.md "Adding a new connector") never
requires touching either of those packages' code.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from context_fabric.connectors.base import FixtureConnectorBase, LiveConnectorBase

_FIXTURE_REGISTRY: dict[str, type[FixtureConnectorBase]] = {}
_LIVE_REGISTRY: dict[str, type[LiveConnectorBase]] = {}


def register_fixture_connector(
    source_system: str, connector_cls: type[FixtureConnectorBase]
) -> None:
    _FIXTURE_REGISTRY[source_system] = connector_cls


def register_live_connector(source_system: str, connector_cls: type[LiveConnectorBase]) -> None:
    _LIVE_REGISTRY[source_system] = connector_cls


def get_fixture_connector_class(source_system: str) -> type[FixtureConnectorBase]:
    try:
        return _FIXTURE_REGISTRY[source_system]
    except KeyError:
        raise KeyError(
            f"no fixture connector registered for source_system={source_system!r}"
        ) from None


def get_live_connector_class(source_system: str) -> type[LiveConnectorBase]:
    try:
        return _LIVE_REGISTRY[source_system]
    except KeyError:
        raise KeyError(
            f"no live connector registered for source_system={source_system!r}"
        ) from None


def registered_source_systems() -> list[str]:
    return sorted(set(_FIXTURE_REGISTRY) | set(_LIVE_REGISTRY))
