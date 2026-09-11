"""GitHubLiveConnector helpers that don't need a network call —
_normalize_login specifically (docs/CONNECTORS.md; the rest of live.py
is exercised manually against a real GitHub account, not here)."""

from __future__ import annotations

import pytest

from context_fabric.connectors.github.live import _normalize_login


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("acme-org", "acme-org"),
        ("https://github.com/acme-org", "acme-org"),
        ("https://github.com/acme-org/", "acme-org"),
        # A URL copied from a specific repo's page carries the repo name
        # along — every REST call here needs just the login.
        ("https://github.com/octocat/Hello-World", "octocat"),
        ("github.com/octocat/Hello-World", "octocat"),
    ],
)
def test_normalize_login_strips_url_and_repo_segment(raw: str, expected: str) -> None:
    assert _normalize_login(raw) == expected
