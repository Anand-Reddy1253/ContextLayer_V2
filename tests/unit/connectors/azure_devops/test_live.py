"""AzureDevOpsLiveConnector helpers that don't need a network call —
_normalize_org_url specifically (docs/CONNECTORS.md; the rest of
live.py is exercised manually against a real org, not here)."""

from __future__ import annotations

import pytest

from context_fabric.connectors.azure_devops.live import _normalize_org_url


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://devonrepo.visualstudio.com", "https://devonrepo.visualstudio.com"),
        # A URL copied from inside a project carries the project name
        # along — every REST call here needs the bare org root.
        ("https://devonrepo.visualstudio.com/DevOnHire", "https://devonrepo.visualstudio.com"),
        ("https://devonrepo.visualstudio.com/DevOnHire/", "https://devonrepo.visualstudio.com"),
        ("https://dev.azure.com/devonrepo", "https://dev.azure.com/devonrepo"),
        ("https://dev.azure.com/devonrepo/DevOnHire", "https://dev.azure.com/devonrepo"),
        ("https://dev.azure.com/devonrepo/", "https://dev.azure.com/devonrepo"),
    ],
)
def test_normalize_org_url_strips_project_segment(raw: str, expected: str) -> None:
    assert _normalize_org_url(raw) == expected
