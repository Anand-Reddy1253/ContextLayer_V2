"""`_browse_url` (connectors/jira/live.py) — Jira's own `self` field
encodes the internal numeric id, not the human key `/browse/` actually
needs. Found live: cards were showing
"https://talentflow-254.atlassian.net/browse/10000", a broken link.
"""

from context_fabric.connectors.jira.live import _browse_url


def test_browse_url_uses_the_key_not_the_internal_id():
    raw_self = "https://talentflow-254.atlassian.net/rest/api/3/issue/10000"
    assert _browse_url(raw_self, "TF-1") == "https://talentflow-254.atlassian.net/browse/TF-1"


def test_browse_url_works_for_project_self_shape_too():
    raw_self = "https://talentflow-254.atlassian.net/rest/api/3/project/10001"
    assert _browse_url(raw_self, "TF") == "https://talentflow-254.atlassian.net/browse/TF"


def test_browse_url_works_for_comment_self_shape_too():
    raw_self = "https://talentflow-254.atlassian.net/rest/api/3/issue/10000/comment/12345"
    assert _browse_url(raw_self, "TF-1") == "https://talentflow-254.atlassian.net/browse/TF-1"
