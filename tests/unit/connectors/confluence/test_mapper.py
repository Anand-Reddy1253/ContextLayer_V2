from context_fabric.connectors.confluence import mapper
from context_fabric.domain.connector_types import (
    ACLReference,
    SourceContainer,
    SourceContent,
    SourceLink,
    SourceObject,
)

SPACE_RAW = {
    "id": "98305",
    "key": "TALENT",
    "name": "TalentFlow",
    # v2's description-format=plain shape (mapper.py's map_space docstring
    # — confirmed against the real live API), not a plain string.
    "description": {
        "plain": {"value": "TalentFlow product documentation.", "representation": "plain"}
    },
    "url": "https://acme.atlassian.net/wiki/spaces/TALENT",
}

ROOT_PAGE_RAW = {
    "id": "131073",
    "spaceId": "98305",
    "parentId": None,
    "title": "Identity Squad Home",
    "status": "current",
    "version": 4,
    "body": "<p>Welcome to the Identity squad space. See AB#301 for the SSO epic.</p>",
    "url": "https://acme.atlassian.net/wiki/spaces/TALENT/pages/131073",
}

CHILD_PAGE_RAW = {
    "id": "131074",
    "spaceId": "98305",
    "parentId": "131073",
    "title": "SSO Design Doc",
    "status": "current",
    "version": 2,
    "body": "<p>Design for SSO. References PR-42 and AB#312.</p>",
    "url": "https://acme.atlassian.net/wiki/spaces/TALENT/pages/131074",
}

ATTACHMENT_RAW = {
    "id": "att131200",
    "pageId": "131074",
    "title": "sso-sequence-diagram.png",
    "mediaType": "image/png",
    "fileSize": 48213,
    "url": "https://acme.atlassian.net/wiki/download/attachments/131074/sso-sequence-diagram.png",
}

COMMENT_RAW = {
    "id": "c131300",
    "pageId": "131074",
    "body": "Looks good, one question about token refresh timing.",
    "author": "identity-squad-lead@acme.example",
    "url": "https://acme.atlassian.net/wiki/spaces/TALENT/pages/131074#comment-131300",
}


def test_map_space() -> None:
    obj = mapper.map_space(SPACE_RAW)
    assert isinstance(obj, SourceContainer)
    assert obj.kind == "SPACE"
    assert obj.native_id == "98305"
    assert obj.attributes["key"] == "TALENT"


def test_map_root_page_parents_to_space() -> None:
    obj = mapper.map_page(ROOT_PAGE_RAW)
    assert isinstance(obj, SourceObject)
    assert obj.kind == "PAGE"
    assert obj.native_id == "131073"
    assert obj.parent_native_id == "98305"
    assert "body" not in obj.attributes  # ADR-003: not eagerly duplicated


def test_map_child_page_parents_to_page() -> None:
    obj = mapper.map_page(CHILD_PAGE_RAW)
    assert obj.parent_native_id == "131073"
    assert obj.name == "SSO Design Doc"
    assert obj.source_version == "2"


def test_map_attachment() -> None:
    obj = mapper.map_attachment(ATTACHMENT_RAW)
    assert obj.native_id == "ATT-att131200"
    assert obj.kind == "ATTACHMENT"
    assert obj.parent_native_id == "131074"
    assert obj.attributes["media_type"] == "image/png"


def test_map_comment() -> None:
    obj = mapper.map_comment(COMMENT_RAW)
    assert obj.native_id == "COMMENT-c131300"
    assert obj.kind == "COMMENT"
    assert obj.parent_native_id == "131074"
    assert "token refresh" in obj.name


def test_map_tombstone() -> None:
    obj = mapper.map_tombstone("131074", "PAGE")
    assert obj.deleted is True
    assert obj.kind == "PAGE"


def test_map_page_content() -> None:
    content = mapper.map_page_content("131073", ROOT_PAGE_RAW)
    assert isinstance(content, SourceContent)
    assert content.mime_type == "text/html"
    assert "Welcome to the Identity squad" in (content.text or "")


def test_map_comment_content() -> None:
    content = mapper.map_comment_content("COMMENT-c131300", COMMENT_RAW)
    assert "token refresh" in (content.text or "")


def test_map_links_from_text_extracts_work_item_and_pr_mentions() -> None:
    links = mapper.map_links_from_text("131074", CHILD_PAGE_RAW["body"])
    assert all(isinstance(link, SourceLink) for link in links)
    kinds = {(link.target_ref, link.link_kind) for link in links}
    assert ("PR-42", "mentions") in kinds
    assert ("AB#312", "mentions") in kinds


def test_map_links_from_text_extracts_jira_key_reference() -> None:
    links = mapper.map_links_from_text("131074", "Tracked in TALENT-2.")
    refs = {link.target_ref for link in links}
    assert "TALENT-2" in refs


def test_map_acl() -> None:
    ref = mapper.map_acl({"native_id": "98305", "acl_ref": {"space": "TALENT"}})
    assert isinstance(ref, ACLReference)
    assert ref.acl_ref["space"] == "TALENT"


def test_map_page_archived_and_restricted_attributes() -> None:
    obj = mapper.map_page(
        {
            **ROOT_PAGE_RAW,
            "status": "archived",
            "restricted": True,
            "restriction_subjects": ["acc-1"],
        }
    )
    assert obj.attributes["archived"] is True
    assert obj.attributes["restricted"] is True
    assert obj.attributes["restriction_subjects"] == ["acc-1"]


def test_map_page_defaults_not_restricted() -> None:
    obj = mapper.map_page(ROOT_PAGE_RAW)
    assert obj.attributes["archived"] is False
    assert obj.attributes["restricted"] is False


def test_map_page_classification_attributes_present() -> None:
    obj = mapper.map_page(ROOT_PAGE_RAW)
    assert "page_type" in obj.attributes
    assert "page_properties" in obj.attributes
    assert "schema_completeness" in obj.attributes
    # ROOT_PAGE_RAW has no labels/page-properties/ADR-shaped title.
    assert obj.attributes["page_type"] is None


def test_map_page_classifies_adr_from_page_properties_macro() -> None:
    raw = {
        **ROOT_PAGE_RAW,
        "body": (
            '<ac:structured-macro ac:name="details"><ac:rich-text-body><table><tbody>'
            "<tr><th>Status</th><td>Accepted</td></tr>"
            "</tbody></table></ac:rich-text-body></ac:structured-macro>"
        ),
        "labels": ["adr"],
    }
    obj = mapper.map_page(raw)
    assert obj.attributes["page_type"] == "adr"
    assert obj.attributes["page_properties"] == {"status": "Accepted"}


def test_map_space_type_attribute() -> None:
    obj = mapper.map_space({**SPACE_RAW, "type": "personal"})
    assert obj.attributes["type"] == "personal"


def test_map_person() -> None:
    obj = mapper.map_person("acc-42", "Ada Lovelace", parent_native_id="98305")
    assert obj.kind == "PERSON"
    assert obj.native_id == "acc-42"
    assert obj.name == "Ada Lovelace"
    assert obj.parent_native_id == "98305"


def test_map_person_falls_back_to_account_id_when_no_display_name() -> None:
    obj = mapper.map_person("acc-42", None, parent_native_id="98305")
    assert obj.name == "acc-42"


def test_map_label() -> None:
    obj = mapper.map_label("payments", parent_native_id="131074")
    assert obj.kind == "LABEL"
    assert obj.native_id == "payments"
    assert obj.name == "payments"
    assert obj.parent_native_id == "131074"


def test_map_blog_post() -> None:
    raw = {
        "id": "999",
        "spaceId": "98305",
        "title": "Q1 announcement",
        "status": "current",
        "version": 1,
        "body": "<p>We shipped SSO.</p>",
        "url": "https://acme.atlassian.net/wiki/spaces/TALENT/blog/999",
        "authorId": "acc-42",
    }
    obj = mapper.map_blog_post(raw)
    assert obj.kind == "BLOG_POST"
    assert obj.native_id == "BLOG-999"
    assert obj.parent_native_id == "98305"
    assert obj.name == "Q1 announcement"


def test_extract_structured_links_falls_back_to_regex_on_malformed_body() -> None:
    """A page whose body fails to parse as XML must not lose reference
    extraction entirely — falls back to the old whole-string regex scan."""
    links = mapper.extract_structured_links("131074", "<p>unterminated <ac:link AB#312")
    refs = {link.target_ref for link in links}
    assert "AB#312" in refs


def test_extract_structured_links_links_to_by_title_and_space() -> None:
    body = (
        "<p>See also <ac:link>"
        '<ri:page ri:content-title="Platform Engineering Home" ri:space-key="PLAT"/>'
        "</ac:link>.</p>"
    )
    links = mapper.extract_structured_links("131076", body)
    links_to = [link for link in links if link.link_kind == "links_to"]
    assert len(links_to) == 1
    assert links_to[0].target_ref == "CONFTITLE:PLAT:Platform Engineering Home"


def test_extract_structured_links_skips_jql_jira_macro() -> None:
    body = (
        '<ac:structured-macro ac:name="jira">'
        '<ac:parameter ac:name="jqlQuery">project = TALENT</ac:parameter>'
        "</ac:structured-macro>"
    )
    links = mapper.extract_structured_links("131076", body)
    assert links == []


def test_map_page_relationship_links_all_confidence_1() -> None:
    links = mapper.map_page_relationship_links(
        "131074",
        space_native_id="98305",
        author_account_id="acc-1",
        label_names=["design", "sso"],
    )
    assert all(link.confidence == 1.0 for link in links)
    by_kind = {link.link_kind: link for link in links}
    assert by_kind["in_space"].target_ref == "CONFSPACE:98305"
    assert by_kind["authored_by"].target_ref == "CONFUSER:acc-1"
    label_refs = {link.target_ref for link in links if link.link_kind == "has_label"}
    assert label_refs == {"CONFLABEL:design", "CONFLABEL:sso"}


def test_map_page_relationship_links_omits_missing_fields() -> None:
    links = mapper.map_page_relationship_links("131074")
    assert links == []


def test_map_comment_relationship_links_reverses_edge_direction() -> None:
    links = mapper.map_comment_relationship_links("COMMENT-c131300", author_account_id="acc-1")
    assert len(links) == 1
    assert links[0].link_kind == "commented_on"
    assert links[0].target_ref == "CONFUSER:acc-1"
    assert links[0].reverse is True


def test_map_comment_relationship_links_empty_without_author() -> None:
    assert mapper.map_comment_relationship_links("COMMENT-c131300", author_account_id=None) == []
