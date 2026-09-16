from context_fabric.connectors.confluence import page_properties, storage_format

_ADR_BODY = (
    '<ac:structured-macro ac:name="details"><ac:rich-text-body><table><tbody>'
    "<tr><th>Status</th><td>Accepted</td></tr>"
    "<tr><th>Context</th><td>We needed event-driven settlement.</td></tr>"
    "<tr><th>Decision</th><td>Move to event sourcing.</td></tr>"
    "<tr><th>Consequences</th><td>Requires new infra.</td></tr>"
    "</tbody></table></ac:rich-text-body></ac:structured-macro>"
)


def test_extract_page_properties_parses_two_column_table():
    root = storage_format.parse_xml(_ADR_BODY)
    assert root is not None
    props = page_properties.extract_page_properties(root)
    assert props == {
        "status": "Accepted",
        "context": "We needed event-driven settlement.",
        "decision": "Move to event sourcing.",
        "consequences": "Requires new infra.",
    }


def test_extract_page_properties_no_macro_returns_empty():
    root = storage_format.parse_xml("<p>No properties table here.</p>")
    assert root is not None
    assert page_properties.extract_page_properties(root) == {}


def test_extract_page_properties_keys_are_snake_cased():
    body = (
        '<ac:structured-macro ac:name="details"><ac:rich-text-body><table><tbody>'
        "<tr><th>Target Release</th><td>2026-Q1</td></tr>"
        "</tbody></table></ac:rich-text-body></ac:structured-macro>"
    )
    root = storage_format.parse_xml(body)
    assert root is not None
    props = page_properties.extract_page_properties(root)
    assert props == {"target_release": "2026-Q1"}


def test_classify_page_by_label_wins_over_title():
    classification = page_properties.classify_page(
        title="Some ordinary page", labels=["adr"], page_properties={}
    )
    assert classification.page_type == "adr"


def test_classify_page_by_page_properties_keys_when_no_label_match():
    classification = page_properties.classify_page(
        title="Untitled", labels=[], page_properties={"target_release": "2026-Q1"}
    )
    assert classification.page_type == "prd"


def test_classify_page_by_title_regex_as_last_resort():
    classification = page_properties.classify_page(
        title="ADR-014 Move settlement to event sourcing", labels=[], page_properties={}
    )
    assert classification.page_type == "adr"


def test_classify_page_unclassified_is_none_not_a_guess():
    """No LLM fallback tier — an unrecognized page stays page_type: null
    rather than a guess (Tier 3's semantic classification is deferred)."""
    classification = page_properties.classify_page(
        title="Random meeting doodle", labels=[], page_properties={}
    )
    assert classification.page_type is None
    assert classification.schema_completeness is None


def test_schema_completeness_reflects_missing_expected_keys():
    """A PRD missing target_release is visibly incomplete, not silently
    null."""
    classification = page_properties.classify_page(
        title="PRD: Something",
        labels=["prd"],
        page_properties={"problem": "x", "goals": "y"},
    )
    assert classification.page_type == "prd"
    # 2 of 5 expected_keys present (problem, goals) — non_goals,
    # requirements, success_metrics missing.
    assert classification.schema_completeness == 2 / 5


def test_schema_completeness_full_when_all_expected_keys_present():
    root = storage_format.parse_xml(_ADR_BODY)
    assert root is not None
    props = page_properties.extract_page_properties(root)
    classification = page_properties.classify_page(
        title="ADR-014", labels=["adr"], page_properties=props
    )
    assert classification.page_type == "adr"
    assert classification.schema_completeness == 1.0


def test_page_type_attributes_shape():
    classification = page_properties.PageClassification(page_type="adr", schema_completeness=0.5)
    attrs = page_properties.page_type_attributes(classification, {"status": "Accepted"})
    assert attrs == {
        "page_type": "adr",
        "page_properties": {"status": "Accepted"},
        "schema_completeness": 0.5,
    }
