from context_fabric.connectors.jira import mapper


def test_map_project() -> None:
    container = mapper.map_project(
        {"key": "TALENT", "name": "TalentFlow", "description": "desc", "url": "https://x/TALENT"}
    )
    assert container.native_id == "TALENT"
    assert container.kind == "PROJECT"


def test_map_issue_maps_known_type_to_kind() -> None:
    node = mapper.map_issue(
        {
            "key": "TALENT-1",
            "project_key": "TALENT",
            "parent_key": None,
            "summary": "SSO Epic",
            "issue_type": "Epic",
            "status": "In Progress",
            "assignee": "Priya Shah",
            "description_text": "",
            "url": "https://x/TALENT-1",
            "updated": "2026-08-20T10:00:00.000+0000",
            "issuelinks": [],
        }
    )
    assert node.kind == "EPIC"
    assert node.parent_native_id == "TALENT"
    assert "description_text" not in node.attributes
    assert "description" not in node.attributes


def test_map_issue_unknown_type_falls_back_to_work_item() -> None:
    node = mapper.map_issue(
        {
            "key": "TALENT-9",
            "project_key": "TALENT",
            "parent_key": None,
            "summary": "Something",
            "issue_type": "Spike",
            "status": "Open",
            "assignee": None,
            "description_text": "",
            "url": "",
            "updated": "",
            "issuelinks": [],
        }
    )
    assert node.kind == "WORK_ITEM"


def test_map_issue_parents_to_issue_when_parent_key_present() -> None:
    node = mapper.map_issue(
        {
            "key": "TALENT-4",
            "project_key": "TALENT",
            "parent_key": "TALENT-2",
            "summary": "Sub-task",
            "issue_type": "Sub-task",
            "status": "Done",
            "assignee": None,
            "description_text": "",
            "url": "",
            "updated": "",
            "issuelinks": [],
        }
    )
    assert node.kind == "SUBTASK"
    assert node.parent_native_id == "TALENT-2"


def test_adf_to_text_flattens_nested_content() -> None:
    adf = {
        "type": "doc",
        "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": "Hello"}]},
            {"type": "paragraph", "content": [{"type": "text", "text": "world AB#312"}]},
        ],
    }
    assert mapper.adf_to_text(adf) == "Hello world AB#312"


def test_adf_to_text_handles_empty_or_missing_body() -> None:
    assert mapper.adf_to_text({}) == ""
    assert mapper.adf_to_text(None) == ""


def test_map_links_extracts_blocking_issuelink_as_depends_on() -> None:
    links = mapper.map_links(
        {
            "key": "TALENT-2",
            "description_text": "",
            "issuelinks": [{"type_name": "Blocks", "target_key": "TALENT-3"}],
        }
    )
    assert links[0].from_native_id == "TALENT-2"
    assert links[0].target_ref == "TALENT-3"
    assert links[0].link_kind == "depends_on"


def test_map_links_extracts_relates_issuelink_as_relates_to() -> None:
    links = mapper.map_links(
        {
            "key": "TALENT-4",
            "description_text": "",
            "issuelinks": [{"type_name": "Relates", "target_key": "TALENT-1"}],
        }
    )
    assert links[0].target_ref == "TALENT-1"
    assert links[0].link_kind == "relates_to"


def test_map_links_skips_issuelink_with_no_target() -> None:
    links = mapper.map_links(
        {"key": "TALENT-2", "description_text": "", "issuelinks": [{"type_name": "Blocks"}]}
    )
    assert links == []


def test_map_links_extracts_text_mentions_from_description() -> None:
    links = mapper.map_links(
        {
            "key": "TALENT-2",
            "description_text": "See AB#312, PR-42 and acme/talentflow-api#7.",
            "issuelinks": [],
        }
    )
    refs = {link.target_ref for link in links}
    assert refs == {"AB#312", "PR-42", "acme/talentflow-api#7"}


def test_map_comment_links_extracts_text_mentions() -> None:
    links = mapper.map_comment_links({"id": "9001", "body_text": "See PR-42."}, "TALENT-2")
    assert links[0].from_native_id == "COMMENT-9001"
    assert links[0].target_ref == "PR-42"
