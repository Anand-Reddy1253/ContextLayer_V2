import pytest

from context_fabric.connectors.confluence.fixture import ConfluenceFixtureConnector
from context_fabric.domain.connector_types import SourceObject
from context_fabric.domain.errors import NotFound


@pytest.fixture
def connector() -> ConfluenceFixtureConnector:
    return ConfluenceFixtureConnector()


async def _all_children(
    connector: ConfluenceFixtureConnector, parent_id: str
) -> list[SourceObject]:
    """Follows cursor pagination (fixture pages 2-at-a-time, PAGE_SIZE=2)
    to collect every child — a single list_children() call can silently
    truncate a same-parent result set that has more than 2 items now that
    PERSON/LABEL nodes are mixed in alongside PAGE/ATTACHMENT/COMMENT."""
    items: list[SourceObject] = []
    cursor: str | None = None
    while True:
        page = await connector.list_children(parent_id, cursor)
        items.extend(page.items)
        if page.next_cursor is None:
            return items
        cursor = page.next_cursor


async def test_discover_containers_returns_spaces(connector: ConfluenceFixtureConnector) -> None:
    containers = await connector.discover_containers()
    assert {c.native_id for c in containers} == {"98305", "98306"}
    assert all(c.kind == "SPACE" for c in containers)


async def test_list_children_walks_space_to_page_to_leaves(
    connector: ConfluenceFixtureConnector,
) -> None:
    space_children = await _all_children(connector, "98305")
    page_ids = {c.native_id for c in space_children if c.kind == "PAGE"}
    assert page_ids == {"131073", "131076"}
    # Both top-level pages in this space share the same author — one
    # PERSON node, not two, dedup'd by account_id.
    person_ids = {c.native_id for c in space_children if c.kind == "PERSON"}
    assert person_ids == {"acc-identity-lead"}
    # Top-level pages' own labels are emitted as their siblings here
    # (ordering: see fixture.py's own docstring on why) — 131073 is
    # labeled "home", 131076 "adr"/"decision".
    label_ids = {c.native_id for c in space_children if c.kind == "LABEL"}
    assert label_ids == {"home", "adr", "decision"}

    page_children = await _all_children(connector, "131073")
    # 131073's own child page is 131074 — its author (same person, still
    # deduped) and its own "design" label are emitted as siblings before
    # it, ahead of it in this same list.
    ids_by_kind: dict[str, set[str]] = {}
    for c in page_children:
        ids_by_kind.setdefault(c.kind, set()).add(c.native_id)
    assert ids_by_kind["PAGE"] == {"131074"}
    assert ids_by_kind["PERSON"] == {"acc-identity-lead"}
    assert ids_by_kind["LABEL"] == {"design"}

    leaf_children = await _all_children(connector, "131074")
    kinds_by_native_id = {c.native_id: c.kind for c in leaf_children}
    assert kinds_by_native_id["ATT-att131200"] == "ATTACHMENT"
    assert kinds_by_native_id["COMMENT-c131300"] == "COMMENT"
    # The comment's author becomes a PERSON sibling here too.
    assert kinds_by_native_id["identity-squad-lead@acme.example"] == "PERSON"
    # 131074's own label ("design") is NOT re-listed as its own child —
    # it already exists as 131074's sibling (asserted above) and lives
    # there in the tree, not nested under the one page that happens to
    # carry it.
    assert "design" not in kinds_by_native_id


async def test_list_children_emits_person_for_page_author(
    connector: ConfluenceFixtureConnector,
) -> None:
    space_children = await _all_children(connector, "98305")
    person = next(c for c in space_children if c.kind == "PERSON")
    assert person.native_id == "acc-identity-lead"
    assert person.name == "Identity Squad Lead"


async def test_get_object_resolves_page_attachment_and_comment(
    connector: ConfluenceFixtureConnector,
) -> None:
    page = await connector.get_object("131074")
    assert page.kind == "PAGE"

    attachment = await connector.get_object("ATT-att131200")
    assert attachment.kind == "ATTACHMENT"

    comment = await connector.get_object("COMMENT-c131300")
    assert comment.kind == "COMMENT"

    with pytest.raises(NotFound):
        await connector.get_object("does-not-exist")


async def test_get_content_fetches_page_body_on_demand(
    connector: ConfluenceFixtureConnector,
) -> None:
    content = await connector.get_content("131074")
    assert "SSO" in (content.text or "")


async def test_get_links_extracts_mentions_from_page_body(
    connector: ConfluenceFixtureConnector,
) -> None:
    links = await connector.get_links("131074")
    refs = {link.target_ref for link in links}
    assert "PR-42" in refs
    assert "AB#312" in refs


async def test_get_links_emits_tier1_relationship_edges(
    connector: ConfluenceFixtureConnector,
) -> None:
    links = await connector.get_links("131074")
    by_kind = {link.link_kind: link for link in links}
    assert by_kind["in_space"].target_ref == "CONFSPACE:98305"
    assert by_kind["in_space"].confidence == 1.0
    assert by_kind["authored_by"].target_ref == "CONFUSER:acc-identity-lead"
    assert by_kind["authored_by"].confidence == 1.0


async def test_get_links_emits_has_label(connector: ConfluenceFixtureConnector) -> None:
    links = await connector.get_links("131074")
    label_links = [link for link in links if link.link_kind == "has_label"]
    assert {link.target_ref for link in label_links} == {"CONFLABEL:design"}


async def test_get_links_on_comment_emits_commented_on(
    connector: ConfluenceFixtureConnector,
) -> None:
    links = await connector.get_links("COMMENT-c131300")
    commented_on = [link for link in links if link.link_kind == "commented_on"]
    assert len(commented_on) == 1
    assert commented_on[0].target_ref == "CONFUSER:identity-squad-lead@acme.example"
    assert commented_on[0].reverse is True


async def test_get_links_structured_extraction_on_adr_page(
    connector: ConfluenceFixtureConnector,
) -> None:
    """131076 exercises the full Tier 2 macro walk: a cross-space
    ri:page link (title+space, no content-id), a ri:user mention, a
    jira key macro, and an include/transclusion macro."""
    links = await connector.get_links("131076")
    by_kind: dict[str, list[str]] = {}
    for link in links:
        by_kind.setdefault(link.link_kind, []).append(link.target_ref)

    assert "CONFTITLE:PLAT:Platform Engineering Home" in by_kind["links_to"]
    assert "CONFTITLE:PLAT:Platform Engineering Home" in by_kind["transcludes"]
    assert "CONFUSER:acc-identity-lead" in by_kind["mentions"]
    assert "TALENT-9" in by_kind["mentions"]


async def test_get_acl_reference(connector: ConfluenceFixtureConnector) -> None:
    ref = await connector.get_acl_reference("98305")
    assert ref.acl_ref["space"] == "TALENT"


async def test_get_changes_is_always_empty(connector: ConfluenceFixtureConnector) -> None:
    changes = await connector.get_changes()
    assert changes.items == []
    assert changes.has_more is False
