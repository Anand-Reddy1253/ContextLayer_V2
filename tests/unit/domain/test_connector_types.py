from context_fabric.domain.connector_types import (
    ACLReference,
    ChangePage,
    Page,
    SourceContainer,
    SourceContent,
    SourceLink,
    SourceObject,
)


def test_source_container():
    c = SourceContainer(id="proj-1", name="TalentFlow", kind="PROJECT", native_id="proj-1")
    assert c.parent_id is None
    assert c.attributes == {}


def test_source_object_tombstone():
    obj = SourceObject(
        native_id="312", kind="WORK_ITEM", name="Add SSO callback", deleted=True
    )
    assert obj.deleted is True


def test_source_content():
    content = SourceContent(
        native_id="312",
        mime_type="text/plain",
        text="Implement SSO callback handling.",
        uri="https://dev.azure.com/acme/_workitems/edit/312",
    )
    assert content.text is not None


def test_source_link_default_kind():
    link = SourceLink(from_native_id="commit-abc", target_ref="AB#312")
    assert link.link_kind == "mentions"


def test_acl_reference():
    ref = ACLReference(native_id="312", acl_ref={"group": "identity-squad"})
    assert ref.acl_ref["group"] == "identity-squad"


def test_page_generic_of_source_containers():
    page: Page[SourceContainer] = Page(
        items=[SourceContainer(id="p1", name="X", kind="PROJECT", native_id="p1")],
        next_cursor="cursor-2",
    )
    assert len(page.items) == 1
    assert page.next_cursor == "cursor-2"


def test_change_page():
    change_page = ChangePage(
        items=[SourceObject(native_id="1", kind="WORK_ITEM", name="a", deleted=True)],
        has_more=False,
    )
    assert change_page.items[0].deleted is True
    assert change_page.has_more is False
