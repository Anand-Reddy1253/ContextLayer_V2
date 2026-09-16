"""Confluence relationship extraction end-to-end (docs/CONNECTORS.md):
Tier 1 (IN_SPACE/AUTHORED_BY/COMMENTED_ON/HAS_LABEL) and Tier 2 (LINKS_TO/
TRANSCLUDES/mentions via structured body parsing, including the CONFTITLE:
title+space name-resolution path a plain regex could never handle).

Uses a dedicated fixtures_dir (tests/fixtures/confluence_relext/, large/
distinctive ids: 9020000+/9021000+, "-relext" account ids) rather than the
shared fixtures/confluence/ data — this shared dev database also holds
real data from earlier live-connector smoke testing, and
get_by_technical_identity_any_instance's own docstring already documents
that a small, plausible-looking native_id (a bare "98305") can collide
with — or resolve ahead of — this test's own nodes (same reasoning as
tests/integration/retrieval/test_scope_resolution.py's own large-id
convention).
"""

from pathlib import Path

from context_fabric.connectors.confluence.fixture import ConfluenceFixtureConnector
from context_fabric.domain.enums import EdgeOrigin, EdgeState, EdgeType
from context_fabric.persistence.repositories.edge import EdgeRepository
from context_fabric.persistence.repositories.node import NodeRepository
from context_fabric.synchronization import sync_source

_INSTANCE = "confluence-relext-test"
_FIXTURES_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "confluence_relext"


def _connector() -> ConfluenceFixtureConnector:
    return ConfluenceFixtureConnector(fixtures_dir=_FIXTURES_DIR)


async def test_page_gets_in_space_and_authored_by_edges(db_session):
    await sync_source(db_session, _connector(), source_instance_id=_INSTANCE)

    node_repo = NodeRepository(db_session)
    edge_repo = EdgeRepository(db_session)
    page = await node_repo.get_by_technical_identity("confluence", _INSTANCE, "9021002")
    space = await node_repo.get_by_technical_identity("confluence", _INSTANCE, "9020001")
    person = await node_repo.get_by_technical_identity(
        "confluence", _INSTANCE, "acc-relext-identity-lead"
    )
    assert page is not None and space is not None and person is not None

    edges = await edge_repo.list_from(page.id)
    in_space = [e for e in edges if e.type is EdgeType.IN_SPACE]
    authored_by = [e for e in edges if e.type is EdgeType.AUTHORED_BY]

    assert len(in_space) == 1
    assert in_space[0].dst_id == space.id
    assert in_space[0].origin is EdgeOrigin.SYNC_STRUCTURAL
    assert in_space[0].state is EdgeState.ACTIVE  # confidence 1.0 auto-confirms

    assert len(authored_by) == 1
    assert authored_by[0].dst_id == person.id
    assert authored_by[0].state is EdgeState.ACTIVE


async def test_page_gets_has_label_edges(db_session):
    await sync_source(db_session, _connector(), source_instance_id=_INSTANCE)

    node_repo = NodeRepository(db_session)
    edge_repo = EdgeRepository(db_session)
    page = await node_repo.get_by_technical_identity("confluence", _INSTANCE, "9021002")
    label = await node_repo.get_by_technical_identity("confluence", _INSTANCE, "design")
    assert page is not None and label is not None

    edges = await edge_repo.list_from(page.id)
    has_label = [e for e in edges if e.type is EdgeType.HAS_LABEL]
    assert len(has_label) == 1
    assert has_label[0].dst_id == label.id


async def test_comment_author_gets_commented_on_edge_to_comment(db_session):
    await sync_source(db_session, _connector(), source_instance_id=_INSTANCE)

    node_repo = NodeRepository(db_session)
    edge_repo = EdgeRepository(db_session)
    comment = await node_repo.get_by_technical_identity(
        "confluence", _INSTANCE, "COMMENT-c9021300"
    )
    person = await node_repo.get_by_technical_identity(
        "confluence", _INSTANCE, "identity-squad-lead-relext@acme.example"
    )
    assert comment is not None and person is not None

    edges = await edge_repo.list_from(person.id)
    commented_on = [e for e in edges if e.type is EdgeType.COMMENTED_ON]
    assert len(commented_on) == 1
    assert commented_on[0].dst_id == comment.id


async def test_links_to_resolves_by_title_and_space_key(db_session):
    """The one genuinely new resolution path: a page-link macro that only
    carries a title+space-key (no ri:content-id — a cross-space link)
    resolves via NodeRepository.get_by_attribute + find_by_name_under,
    not a plain native_id lookup.

    Synced twice: this is a genuinely *cross-space* reference (TALENT9's
    ADR page links into PLAT9), and BFS processes one space's whole
    subtree before ever starting the next — the exact same "unresolved on
    this pass, resolves on the next" behavior link_extraction.py already
    documents for cross-connector references (see
    test_link_extraction.py's own cross-connector test, which syncs its
    two connectors in dependency order for the same reason)."""
    connector = _connector()
    await sync_source(db_session, connector, source_instance_id=_INSTANCE)
    await sync_source(db_session, connector, source_instance_id=_INSTANCE)

    node_repo = NodeRepository(db_session)
    edge_repo = EdgeRepository(db_session)
    adr_page = await node_repo.get_by_technical_identity("confluence", _INSTANCE, "9021004")
    plat_home = await node_repo.get_by_technical_identity("confluence", _INSTANCE, "9021003")
    assert adr_page is not None and plat_home is not None

    edges = await edge_repo.list_from(adr_page.id)
    links_to = [e for e in edges if e.type is EdgeType.LINKS_TO]
    assert len(links_to) == 1
    assert links_to[0].dst_id == plat_home.id


async def test_transcludes_resolves_by_title_and_space_key(db_session):
    # Cross-space reference — see test_links_to_resolves_by_title_and_
    # space_key's docstring for why this needs a second sync pass.
    connector = _connector()
    await sync_source(db_session, connector, source_instance_id=_INSTANCE)
    await sync_source(db_session, connector, source_instance_id=_INSTANCE)

    node_repo = NodeRepository(db_session)
    edge_repo = EdgeRepository(db_session)
    adr_page = await node_repo.get_by_technical_identity("confluence", _INSTANCE, "9021004")
    plat_home = await node_repo.get_by_technical_identity("confluence", _INSTANCE, "9021003")
    assert adr_page is not None and plat_home is not None

    edges = await edge_repo.list_from(adr_page.id)
    transcludes = [e for e in edges if e.type is EdgeType.TRANSCLUDES]
    assert len(transcludes) == 1
    assert transcludes[0].dst_id == plat_home.id


async def test_ri_user_mention_resolves_to_person_node(db_session):
    await sync_source(db_session, _connector(), source_instance_id=_INSTANCE)

    node_repo = NodeRepository(db_session)
    edge_repo = EdgeRepository(db_session)
    adr_page = await node_repo.get_by_technical_identity("confluence", _INSTANCE, "9021004")
    person = await node_repo.get_by_technical_identity(
        "confluence", _INSTANCE, "acc-relext-identity-lead"
    )
    assert adr_page is not None and person is not None

    edges = await edge_repo.list_from(adr_page.id)
    mentions_person = [
        e for e in edges if e.type is EdgeType.MENTIONS and e.dst_id == person.id
    ]
    assert len(mentions_person) == 1


async def test_structured_link_does_not_duplicate_via_plain_text_fallback(db_session):
    """The macro-walk (Tier 2) replaced the old whole-string regex scan —
    a page-link macro's own ri:content-id/title never bleeds into
    plain_text, so the same reference is never extracted twice. Synced
    twice — see test_links_to_resolves_by_title_and_space_key's
    docstring for why this specific cross-space reference needs it."""
    connector = _connector()
    await sync_source(db_session, connector, source_instance_id=_INSTANCE)
    await sync_source(db_session, connector, source_instance_id=_INSTANCE)

    node_repo = NodeRepository(db_session)
    edge_repo = EdgeRepository(db_session)
    adr_page = await node_repo.get_by_technical_identity("confluence", _INSTANCE, "9021004")
    plat_home = await node_repo.get_by_technical_identity("confluence", _INSTANCE, "9021003")
    assert adr_page is not None and plat_home is not None

    edges = await edge_repo.list_from(adr_page.id)
    to_plat_home = [e for e in edges if e.dst_id == plat_home.id]
    # Exactly two real, distinct relationships to that page (LINKS_TO from
    # the ac:link, TRANSCLUDES from the include macro) — never a third
    # RELATED_TO/MENTIONS duplicate from a plain-text rescan of the same
    # macro's title/id.
    assert {e.type for e in to_plat_home} == {EdgeType.LINKS_TO, EdgeType.TRANSCLUDES}
    assert len(to_plat_home) == 2


async def test_resync_does_not_duplicate_tier1_edges(db_session):
    connector = _connector()
    await sync_source(db_session, connector, source_instance_id=_INSTANCE)
    node_repo = NodeRepository(db_session)
    edge_repo = EdgeRepository(db_session)
    page = await node_repo.get_by_technical_identity("confluence", _INSTANCE, "9021002")
    first_run = len(await edge_repo.list_from(page.id))

    await sync_source(db_session, connector, source_instance_id=_INSTANCE)
    second_run = len(await edge_repo.list_from(page.id))

    assert first_run == second_run
    assert first_run > 0
