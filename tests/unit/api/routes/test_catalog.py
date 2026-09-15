"""Unit tests for the pure helper functions behind GET /catalog/search-cards
(docs/UI.md "Search") — no DB needed, so these run at the unit tier.
`_score_match` and `_reachable_ids` are the two pieces of actual logic;
`_locator_json` is the shape a downstream agent hands to a native
per-vendor MCP server.
"""

from datetime import UTC, datetime
from uuid import uuid4

from context_fabric.api.routes.catalog import (
    _business_context_for,
    _infer_kind_filter,
    _locator_json,
    _native_call_json,
    _reachable_ids,
    _score_match,
)
from context_fabric.domain.enums import Layer
from context_fabric.domain.node import Node


def _node(
    name: str,
    description: str | None = None,
    *,
    attributes: dict | None = None,
    native_id: str = "312",
) -> Node:
    now = datetime.now(UTC)
    return Node(
        layer=Layer.TECHNICAL,
        kind="WORK_ITEM",
        name=name,
        description=description,
        source_system="azure_devops",
        source_instance_id="ado-acme",
        native_id=native_id,
        path="ado_acme.312",
        attributes={
            "url": "https://dev.azure.com/acme/_workitems/edit/312",
            **(attributes or {}),
        },
        first_seen_at=now,
        last_seen_at=now,
        created_at=now,
        updated_at=now,
    )


def _generic_node(
    *, source_system: str, kind: str, native_id: str, attributes: dict | None = None
) -> Node:
    now = datetime.now(UTC)
    return Node(
        layer=Layer.TECHNICAL,
        kind=kind,
        name="x",
        source_system=source_system,
        source_instance_id="instance",
        native_id=native_id,
        path="x.y",
        attributes=attributes or {},
        first_seen_at=now,
        last_seen_at=now,
        created_at=now,
        updated_at=now,
    )


def test_score_match_exact_name_scores_highest():
    node = _node("SSO")
    assert _score_match("sso", node) == 1.0


def test_score_match_prefix_scores_below_exact():
    node = _node("SSO Login Flow")
    assert _score_match("sso", node) == 0.9


def test_score_match_substring_scores_below_prefix():
    node = _node("Implement SSO for gateway")
    assert _score_match("sso", node) == 0.7


def test_score_match_description_only_scores_lowest():
    node = _node("Login flow", description="Covers SSO rollout details.")
    assert _score_match("sso", node) == 0.4


def test_score_match_no_match_returns_none():
    node = _node("Payments reconciliation", description="Nothing about auth here.")
    assert _score_match("sso", node) is None


def test_score_match_exact_native_id_scores_highest():
    node = _node("Vacancy edit form silently truncates descriptions", native_id="TF-1")
    assert _score_match("tf-1", node) == 1.0


def test_score_match_native_id_prefix_scores_below_exact():
    node = _node("Some ticket", native_id="TF-142")
    assert _score_match("tf-1", node) == 0.9


def test_score_match_native_id_substring_scores_below_prefix():
    node = _node("Some ticket", native_id="AB#296")
    assert _score_match("296", node) == 0.7


def test_score_match_uses_whichever_of_name_or_native_id_scores_higher():
    # native_id is an exact match (1.0), name only a substring (0.7) —
    # the id lookup wins.
    node = _node("Implement SSO for gateway", native_id="SSO")
    assert _score_match("sso", node) == 1.0


def test_score_match_single_word_typo_matches_via_fuzzy_tier():
    node = _node("Edit Vacancy form")
    assert _score_match("vaccancy", node) == 0.25


def test_score_match_multi_word_query_with_one_typo_matches_via_fuzzy_tier():
    node = _node("Edit Vacancy form", description="Users report a problem on save.")
    assert _score_match("vaccancy problm", node) == 0.25


def test_score_match_unrelated_typo_query_does_not_fuzzy_match():
    node = _node("Payments reconciliation")
    assert _score_match("vaccancy", node) is None


def test_score_match_multi_word_query_matches_across_fields_any_order():
    node = _node("Edit Vacancy form", description="Users report a bug on save.")
    assert _score_match("vacancy bug", node) == 0.3


def test_score_match_multi_word_query_all_terms_must_be_present():
    node = _node("Edit Vacancy form", description="Nothing about the other word here.")
    assert _score_match("vacancy bug", node) is None


def test_score_match_single_word_query_unaffected_by_multi_term_fallback():
    # A single-word query that doesn't match anything still returns None —
    # the multi-term fallback only applies when there's more than one term.
    node = _node("Payments reconciliation")
    assert _score_match("nonexistent", node) is None


def test_infer_kind_filter_strips_the_kind_word_from_the_query():
    kinds, remaining = _infer_kind_filter("vacancy bug")
    assert kinds == {"BUG", "ISSUE"}
    assert remaining == "vacancy"


def test_infer_kind_filter_no_kind_word_returns_none_and_original_query():
    kinds, remaining = _infer_kind_filter("vacancy edit form")
    assert kinds is None
    assert remaining == "vacancy edit form"


def test_infer_kind_filter_unions_multiple_kind_words():
    kinds, remaining = _infer_kind_filter("task or story about vacancy")
    assert kinds == {"TASK", "STORY"}
    assert remaining == "or about vacancy"


def test_infer_kind_filter_is_case_insensitive():
    kinds, remaining = _infer_kind_filter("Vacancy Bug")
    assert kinds == {"BUG", "ISSUE"}
    assert remaining == "Vacancy"


def test_score_match_llm_keyword_hit_scores_between_name_substring_and_description():
    node = _node("Login flow", attributes={"llm_keywords": ["sso", "oauth"]})
    assert _score_match("sso", node) == 0.55


def test_score_match_llm_abstract_hit_scores_lowest_when_no_vendor_description():
    node = _node("Login flow", attributes={"llm_abstract": "Explains the SSO rollout plan."})
    assert _score_match("sso", node) == 0.35


def test_score_match_vendor_description_outranks_llm_abstract_at_equal_match():
    node = _node(
        "Login flow",
        description="Covers SSO rollout details.",
        attributes={"llm_abstract": "Also mentions SSO somewhere."},
    )
    assert _score_match("sso", node) == 0.4


def test_locator_json_pulls_identity_and_url_from_attributes():
    node = _node("SSO")
    locator = _locator_json(node)
    assert locator == {
        "source_system": "azure_devops",
        "source_instance_id": "ado-acme",
        "native_id": "312",
        "kind": "WORK_ITEM",
        "url": "https://dev.azure.com/acme/_workitems/edit/312",
        "native_call": {
            "tool": "wit_get_work_items_batch",
            "params": {"project": "acme", "ids": ["312"]},
        },
    }


def test_native_call_json_azure_devops_extracts_project_guid_from_url():
    node = _generic_node(
        source_system="azure_devops",
        kind="WORK_ITEM",
        native_id="182",
        attributes={
            "url": "https://devonrepo.visualstudio.com/58eab199-102b-4961-869c-e6aa3a792b10/_apis/wit/workItems/182"
        },
    )
    assert _native_call_json(node) == {
        "tool": "wit_get_work_items_batch",
        "params": {"project": "58eab199-102b-4961-869c-e6aa3a792b10", "ids": ["182"]},
    }


def test_native_call_json_github_pull_request():
    node = _generic_node(
        source_system="github", kind="PULL_REQUEST", native_id="acme-org/identity-service#7"
    )
    assert _native_call_json(node) == {
        "tool": "get_pull_request",
        "params": {"owner": "acme-org", "repo": "identity-service", "pullNumber": 7},
    }


def test_native_call_json_github_issue():
    node = _generic_node(
        source_system="github", kind="ISSUE", native_id="acme-org/identity-service#3"
    )
    assert _native_call_json(node) == {
        "tool": "get_issue",
        "params": {"owner": "acme-org", "repo": "identity-service", "issue_number": 3},
    }


def test_native_call_json_github_file():
    node = _generic_node(
        source_system="github", kind="FILE", native_id="acme-org/identity-service@main:src/app.py"
    )
    assert _native_call_json(node) == {
        "tool": "get_file_contents",
        "params": {
            "owner": "acme-org",
            "repo": "identity-service",
            "path": "src/app.py",
            "ref": "main",
        },
    }


def test_native_call_json_github_repository_returns_none():
    node = _generic_node(
        source_system="github", kind="REPOSITORY", native_id="acme-org/identity-service"
    )
    assert _native_call_json(node) is None


def test_native_call_json_confluence_page():
    node = _generic_node(source_system="confluence", kind="PAGE", native_id="327898")
    assert _native_call_json(node) == {
        "tool": "getConfluencePage",
        "params": {"pageId": "327898"},
    }


def test_native_call_json_jira_issue():
    node = _generic_node(source_system="jira", kind="BUG", native_id="TALENT-3")
    assert _native_call_json(node) == {
        "tool": "getJiraIssue",
        "params": {"issueIdOrKey": "TALENT-3"},
    }


def test_native_call_json_teams_message_with_channel_id():
    node = _generic_node(
        source_system="teams",
        kind="MESSAGE",
        native_id="1700000000001",
        attributes={"channel_id": "19:identity-squad@thread.tacv2"},
    )
    assert _native_call_json(node) == {
        "tool": "get_channel_messages",
        "params": {"channelId": "19:identity-squad@thread.tacv2", "messageId": "1700000000001"},
    }


def test_native_call_json_teams_message_without_channel_id_returns_none():
    node = _generic_node(source_system="teams", kind="MESSAGE", native_id="1700000000001")
    assert _native_call_json(node) is None


def test_native_call_json_unknown_source_system_returns_none():
    node = _generic_node(source_system="unknown", kind="THING", native_id="1")
    assert _native_call_json(node) is None


def _edge(src: str, dst: str, edge_type: str) -> dict:
    return {"src_id": src, "dst_id": dst, "type": edge_type}


def test_reachable_ids_follows_structural_and_binding_edges():
    team, ctxspace, repo = "team", "ctxspace:x", "repo"
    edges = [
        _edge(team, ctxspace, "HAS_CONTEXT_SPACE"),
        _edge(ctxspace, repo, "BINDS"),
    ]
    reachable = _reachable_ids([], edges, team)
    assert reachable == {team, ctxspace, repo}


def test_reachable_ids_does_not_cross_mention_edges():
    # This is the exact shape of the real bug found via live testing:
    # a team's bound repo has a MENTIONS edge to an unrelated work item
    # from a completely different team's data — that must not pull the
    # unrelated item into this team's search scope.
    team, ctxspace, repo, unrelated = "team", "ctxspace:x", "repo", "unrelated-work-item"
    edges = [
        _edge(team, ctxspace, "HAS_CONTEXT_SPACE"),
        _edge(ctxspace, repo, "BINDS"),
        _edge(repo, unrelated, "MENTIONS"),
    ]
    reachable = _reachable_ids([], edges, team)
    assert reachable == {team, ctxspace, repo}
    assert unrelated not in reachable


def test_reachable_ids_unrestricted_when_edge_types_is_none():
    # The Enterprise Graph page's own "scope to node" view intentionally
    # allows any edge type — over-inclusion there is a visual nicety
    # question, not a correctness one.
    a, b = "a", "b"
    edges = [_edge(a, b, "MENTIONS")]
    reachable = _reachable_ids([], edges, a, edge_types=None)
    assert reachable == {a, b}


def test_reachable_ids_root_alone_when_isolated():
    reachable = _reachable_ids([], [], str(uuid4()))
    assert len(reachable) == 1


def _business_node(node_id: str, name: str, attributes: dict) -> dict:
    return {"id": node_id, "layer": "BUSINESS", "name": name, "attributes": attributes}


def test_business_context_for_resolves_from_self_binding():
    team = _business_node("team-1", "Identity Squad", {"criticality_tier": "prod-critical"})
    context = _business_context_for(
        ["repo-1"],
        bind_target_to_ctxspace={"repo-1": "ctxspace:x"},
        ctxspace_to_business={"ctxspace:x": "team-1"},
        business_node_by_id={"team-1": team},
    )
    assert context == {
        "business_node_id": "team-1",
        "business_node_name": "Identity Squad",
        "attributes": {"criticality_tier": "prod-critical"},
    }


def test_business_context_for_falls_back_to_nearest_bound_ancestor():
    # The real-world case this exists for: a work item several levels
    # below its project isn't itself bound — only the project container
    # is — so the work item's own business context must come from
    # walking up to that ancestor, not from a direct binding on itself.
    context = _business_context_for(
        ["work-item-42", "epic-1", "project-1"],
        bind_target_to_ctxspace={"project-1": "ctxspace:x"},
        ctxspace_to_business={"ctxspace:x": "team-1"},
        business_node_by_id={"team-1": _business_node("team-1", "Identity Squad", {})},
    )
    assert context is not None
    assert context["business_node_id"] == "team-1"


def test_business_context_for_prefers_nearest_bound_ancestor_over_farther_one():
    context = _business_context_for(
        ["work-item-42", "epic-1", "project-1"],
        bind_target_to_ctxspace={"epic-1": "ctxspace:near", "project-1": "ctxspace:far"},
        ctxspace_to_business={"ctxspace:near": "team-near", "ctxspace:far": "team-far"},
        business_node_by_id={
            "team-near": _business_node("team-near", "Near Team", {}),
            "team-far": _business_node("team-far", "Far Team", {}),
        },
    )
    assert context is not None
    assert context["business_node_id"] == "team-near"


def test_business_context_for_returns_none_when_nothing_bound():
    context = _business_context_for(
        ["work-item-42", "epic-1"],
        bind_target_to_ctxspace={},
        ctxspace_to_business={},
        business_node_by_id={},
    )
    assert context is None
