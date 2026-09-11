"""Anti-leakage acceptance test (docs/CONNECTORS.md "Anti-leakage test",
AGENTS.md §5): every registered connector's public protocol methods must
return domain/ types, never a vendor-shaped dict or SDK object.

No real connector exists until Phase 4 (Azure DevOps) — the first test
below walks whatever is registered right now (nothing, correctly, per
docs/phases/PHASE-03.md). The second and third tests prove the *checker*
itself actually works — one confirms it catches a real leak, the other
confirms it doesn't false-positive on a correct implementation. This is
the permanent, automated version of PHASE-03's exit-gate instruction to
"temporarily break it... to prove it fails correctly, then revert" — kept
as a standing regression test instead of a one-off manual step, so it
keeps proving the mechanism works through every later phase.
"""

from __future__ import annotations

from typing import Any, get_args, get_origin, get_type_hints

import pytest

from context_fabric.connectors import registry
from context_fabric.domain.connector_types import (
    ACLReference,
    ChangePage,
    Page,
    SourceContainer,
    SourceContent,
    SourceLink,
    SourceObject,
)

PROTOCOL_METHOD_NAMES = (
    "discover_containers",
    "list_children",
    "get_object",
    "get_content",
    "get_changes",
    "get_links",
    "get_acl_reference",
)


def _is_list_of(hint: Any, leaf: type) -> bool:
    return get_origin(hint) is list and get_args(hint) == (leaf,)


def _is_page_of(hint: Any, leaf: type) -> bool:
    # Page[T] is a pydantic generic model: Page[SourceObject] materializes
    # as a real, cached subclass (not a typing._GenericAlias), so
    # typing.get_origin/get_args don't recognize it — pydantic exposes the
    # same information via __pydantic_generic_metadata__ instead.
    metadata = getattr(hint, "__pydantic_generic_metadata__", None)
    if metadata is None:
        return False
    return metadata.get("origin") is Page and metadata.get("args") == (leaf,)


_CHECKS: dict[str, Any] = {
    "discover_containers": lambda hint: _is_list_of(hint, SourceContainer),
    "list_children": lambda hint: _is_page_of(hint, SourceObject),
    "get_object": lambda hint: hint is SourceObject,
    "get_content": lambda hint: hint is SourceContent,
    "get_changes": lambda hint: hint is ChangePage,
    "get_links": lambda hint: _is_list_of(hint, SourceLink),
    "get_acl_reference": lambda hint: hint is ACLReference,
}


def assert_connector_returns_domain_types(connector_cls: type) -> None:
    """Inspects (does not invoke — a generic caller can't know a valid
    native_id for an arbitrary connector) the return-type annotation of
    each protocol method and asserts it is exactly the domain/ shape
    docs/CONNECTORS.md specifies."""
    for method_name in PROTOCOL_METHOD_NAMES:
        method = getattr(connector_cls, method_name, None)
        if method is None:
            raise AssertionError(
                f"{connector_cls.__name__} is missing protocol method {method_name!r}"
            )
        hints = get_type_hints(method)
        return_hint = hints.get("return")
        check = _CHECKS[method_name]
        if return_hint is None or not check(return_hint):
            raise AssertionError(
                f"{connector_cls.__name__}.{method_name} return type "
                f"{return_hint!r} is not the domain/ type required by the "
                "SourceConnector protocol (docs/CONNECTORS.md) — a vendor "
                "payload shape may be leaking across the connector boundary."
            )


def test_every_registered_connector_returns_only_domain_types() -> None:
    source_systems = registry.registered_source_systems()
    for source_system in source_systems:
        try:
            connector_cls = registry.get_fixture_connector_class(source_system)
        except KeyError:
            connector_cls = registry.get_live_connector_class(source_system)
        assert_connector_returns_domain_types(connector_cls)


class _LeakyFakeConnector:
    """Deliberately violates the protocol — get_object returns a raw dict
    instead of a domain/ SourceObject. Exists only to prove the detector
    above actually catches this."""

    source_system = "fake"
    mode = "fixture"

    async def discover_containers(self) -> list[SourceContainer]: ...
    async def list_children(
        self, parent_id: str, cursor: str | None = None
    ) -> Page[SourceObject]: ...
    async def get_object(self, native_id: str) -> dict:  # <-- the leak
        ...
    async def get_content(
        self, native_id: str, version: str | None = None
    ) -> SourceContent: ...
    async def get_changes(self, cursor: str | None = None) -> ChangePage: ...
    async def get_links(self, native_id: str) -> list[SourceLink]: ...
    async def get_acl_reference(self, native_id: str) -> ACLReference: ...


class _CleanFakeConnector:
    """Conforms to the protocol correctly — proves the detector doesn't
    false-positive on a correct implementation."""

    source_system = "fake"
    mode = "fixture"

    async def discover_containers(self) -> list[SourceContainer]: ...
    async def list_children(
        self, parent_id: str, cursor: str | None = None
    ) -> Page[SourceObject]: ...
    async def get_object(self, native_id: str) -> SourceObject: ...
    async def get_content(
        self, native_id: str, version: str | None = None
    ) -> SourceContent: ...
    async def get_changes(self, cursor: str | None = None) -> ChangePage: ...
    async def get_links(self, native_id: str) -> list[SourceLink]: ...
    async def get_acl_reference(self, native_id: str) -> ACLReference: ...


def test_detector_catches_a_real_vendor_shape_leak() -> None:
    with pytest.raises(AssertionError, match="get_object"):
        assert_connector_returns_domain_types(_LeakyFakeConnector)


def test_detector_passes_a_correct_connector() -> None:
    assert_connector_returns_domain_types(_CleanFakeConnector)
