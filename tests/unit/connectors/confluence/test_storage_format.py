from context_fabric.connectors.confluence import storage_format


def test_ri_page_link_by_content_id():
    body = '<ac:link><ri:page ri:content-id="131075"/></ac:link>'
    parsed = storage_format.parse_storage_format(body)
    assert parsed is not None
    assert len(parsed.page_links) == 1
    assert parsed.page_links[0].content_id == "131075"
    assert parsed.page_links[0].title is None


def test_ri_page_link_by_title_and_space_key():
    body = (
        '<ac:link><ri:page ri:content-title="Platform Engineering Home" '
        'ri:space-key="PLAT"/></ac:link>'
    )
    parsed = storage_format.parse_storage_format(body)
    assert parsed is not None
    ref = parsed.page_links[0]
    assert ref.content_id is None
    assert ref.title == "Platform Engineering Home"
    assert ref.space_key == "PLAT"


def test_ri_user_mention():
    body = '<p>cc <ac:link><ri:user ri:account-id="acc-42"/></ac:link></p>'
    parsed = storage_format.parse_storage_format(body)
    assert parsed is not None
    assert parsed.user_mentions == ["acc-42"]


def test_jira_macro_with_key():
    body = (
        '<ac:structured-macro ac:name="jira">'
        '<ac:parameter ac:name="key">TALENT-9</ac:parameter>'
        "</ac:structured-macro>"
    )
    parsed = storage_format.parse_storage_format(body)
    assert parsed is not None
    assert len(parsed.jira_macros) == 1
    assert parsed.jira_macros[0].key == "TALENT-9"
    assert parsed.jira_macros[0].is_jql is False


def test_jira_macro_jql_variant_has_no_key():
    """The JQL-filter variant has no single resolvable target — is_jql
    marks it so callers skip it rather than mis-extracting a "key" that
    was never there."""
    body = (
        '<ac:structured-macro ac:name="jira">'
        '<ac:parameter ac:name="jqlQuery">project = TALENT</ac:parameter>'
        "</ac:structured-macro>"
    )
    parsed = storage_format.parse_storage_format(body)
    assert parsed is not None
    assert parsed.jira_macros[0].key is None
    assert parsed.jira_macros[0].is_jql is True


def test_include_macro_nested_ri_page_is_found():
    """A real bug this test guards against: the include macro's `page`
    parameter nests ri:page one level deeper than ac:link does
    (ac:structured-macro > ac:parameter > ri:page) — a plain Element.find
    (immediate children only) misses it entirely."""
    body = (
        '<ac:structured-macro ac:name="include">'
        '<ac:parameter ac:name="page">'
        '<ri:page ri:content-title="Onboarding" ri:space-key="TALENT"/>'
        "</ac:parameter>"
        "</ac:structured-macro>"
    )
    parsed = storage_format.parse_storage_format(body)
    assert parsed is not None
    assert len(parsed.includes) == 1
    assert parsed.includes[0].title == "Onboarding"
    assert parsed.includes[0].space_key == "TALENT"


def test_excerpt_include_macro_also_recognized():
    body = (
        '<ac:structured-macro ac:name="excerpt-include">'
        '<ac:parameter ac:name="page">'
        '<ri:page ri:content-id="131075"/>'
        "</ac:parameter>"
        "</ac:structured-macro>"
    )
    parsed = storage_format.parse_storage_format(body)
    assert parsed is not None
    assert parsed.includes[0].content_id == "131075"


def test_plain_text_excludes_macro_internals():
    """A macro's own parameter values (a page title, a Jira key) must not
    leak into plain_text — otherwise the same reference gets extracted
    twice, once structurally and once via the plain-text regex fallback."""
    body = (
        "<p>See the design doc.</p>"
        '<ac:structured-macro ac:name="jira">'
        '<ac:parameter ac:name="key">TALENT-9</ac:parameter>'
        "</ac:structured-macro>"
    )
    parsed = storage_format.parse_storage_format(body)
    assert parsed is not None
    assert "TALENT-9" not in parsed.plain_text
    assert "design doc" in parsed.plain_text


def test_ac_link_human_label_text_stays_in_plain_text():
    """The link macro's own subtree is consumed for its ri:page/ri:user
    *reference*, but a human-readable label alongside it (the link's own
    visible text) is still real prose and must survive into plain_text."""
    body = (
        "<ac:link><ri:page ri:content-id=\"131075\"/>"
        '<ac:plain-text-link-body><![CDATA[see the platform docs]]></ac:plain-text-link-body>'
        "</ac:link>"
    )
    parsed = storage_format.parse_storage_format(body)
    assert parsed is not None
    assert "see the platform docs" in parsed.plain_text


def test_plain_text_still_matches_existing_cross_reference_patterns():
    """Non-macro references (a bare "AB#123" in prose) must still be
    findable in plain_text — this is what extract_cross_references
    later runs against."""
    body = "<p>Fixes AB#312 and mentions PR-42.</p>"
    parsed = storage_format.parse_storage_format(body)
    assert parsed is not None
    assert "AB#312" in parsed.plain_text
    assert "PR-42" in parsed.plain_text


def test_empty_body_returns_empty_result():
    parsed = storage_format.parse_storage_format("")
    assert parsed is not None
    assert parsed.page_links == []
    assert parsed.plain_text == ""


def test_malformed_body_returns_none_not_raises():
    parsed = storage_format.parse_storage_format("<p>unterminated <ac:link")
    assert parsed is None


def test_parse_xml_malformed_returns_none():
    assert storage_format.parse_xml("<p>unterminated <ac:link") is None
