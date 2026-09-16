from __future__ import annotations

import pytest

from context_fabric.retrieval.task_ref import UnrecognizedTaskRef, parse_task_ref


def test_parse_ado_task_ref():
    parsed = parse_task_ref("AB#312")
    assert parsed.source_system == "azure_devops"
    assert parsed.native_id == "312"


def test_parse_github_task_ref():
    parsed = parse_task_ref("acme-org/identity-service#42")
    assert parsed.source_system == "github"
    assert parsed.native_id == "acme-org/identity-service#42"


def test_parse_confluence_task_ref():
    parsed = parse_task_ref("CONFPAGE-98765")
    assert parsed.source_system == "confluence"
    assert parsed.native_id == "98765"


def test_parse_jira_task_ref():
    parsed = parse_task_ref("TALENT-2")
    assert parsed.source_system == "jira"
    assert parsed.native_id == "TALENT-2"


def test_ado_pattern_is_not_shadowed_by_jira_pattern():
    # "AB#312" must resolve as azure_devops, not accidentally fall through
    # to a later, broader pattern.
    parsed = parse_task_ref("AB#312")
    assert parsed.source_system == "azure_devops"


def test_unrecognized_task_ref_raises():
    with pytest.raises(UnrecognizedTaskRef):
        parse_task_ref("not a task ref at all")
