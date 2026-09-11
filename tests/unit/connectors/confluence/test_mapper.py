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
    "description": "TalentFlow product documentation.",
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
