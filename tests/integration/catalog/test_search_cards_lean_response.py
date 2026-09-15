"""Response size control on GET /catalog/search-cards
(api/routes/catalog.py) — found live: once nodes carry a real embedding
(attributes.embedding, a 700+-float array), the unmodified response was
serializing that vector into every card's own node, every ancestor, and
every linked node, on top of their full attribute bags. `_node_json` now
strips `embedding` unconditionally and drops the whole attribute bag for
ancestors/links (context around a match, not the match itself — same
"lean" principle already applied to /entities/search).
"""

from datetime import UTC, datetime

from context_fabric.api.routes.catalog import search_cards
from context_fabric.domain.edge import Edge
from context_fabric.domain.enums import EdgeOrigin, EdgeState, EdgeType, Layer
from context_fabric.domain.node import Node
from context_fabric.persistence.repositories.edge import EdgeRepository
from context_fabric.persistence.repositories.node import NodeRepository

_FAKE_VECTOR = [0.1] * 768


async def _make_node(node_repo: NodeRepository, *, name: str, native_id: str, path: str):
    now = datetime.now(UTC)
    return await node_repo.create(
        Node(
            layer=Layer.TECHNICAL,
            kind="PAGE",
            name=name,
            source_system="confluence",
            source_instance_id="conf-lean-test",
            native_id=native_id,
            path=path,
            attributes={"embedding": _FAKE_VECTOR, "labels": ["adr"], "status": "current"},
            first_seen_at=now,
            last_seen_at=now,
            created_at=now,
            updated_at=now,
        )
    )


async def test_search_cards_never_serializes_the_embedding_vector(db_session):
    node_repo = NodeRepository(db_session)
    edge_repo = EdgeRepository(db_session)
    now = datetime.now(UTC)

    await _make_node(node_repo, name="Lean Test Space", native_id="LEAN-0", path="lean0")
    match = await _make_node(
        node_repo, name="Lean Test Match Page", native_id="LEAN-1", path="lean0.lean1"
    )
    linked = await _make_node(
        node_repo, name="Lean Test Linked Page", native_id="LEAN-2", path="lean0.lean2"
    )
    await edge_repo.create(
        Edge(
            src_id=match.id,
            dst_id=linked.id,
            type=EdgeType.MENTIONS,
            origin=EdgeOrigin.SYNC_EXTRACTED,
            state=EdgeState.PROPOSED,
            confidence=0.85,
            first_seen_at=now,
            last_seen_at=now,
        )
    )

    cards = await search_cards(q="Lean Test Match", session=db_session)
    assert len(cards) == 1
    card = cards[0]

    # The match itself: embedding stripped, everything else kept.
    assert "embedding" not in card["node"]["attributes"]
    assert card["node"]["attributes"]["labels"] == ["adr"]

    # Ancestors and links: no attributes at all, not just no embedding —
    # the UI never reads them, so they shouldn't cost any tokens.
    assert len(card["ancestors"]) == 1
    assert card["ancestors"][0]["node"]["attributes"] == {}
    assert card["ancestors"][0]["node"]["name"] == "Lean Test Space"

    assert len(card["links"]) == 1
    assert card["links"][0]["node"]["attributes"] == {}
    assert card["links"][0]["node"]["name"] == "Lean Test Linked Page"
    # The link's locator (used by the UI's "open" button) still works —
    # only the bulky attributes bag was dropped, not the identity/url.
    assert card["links"][0]["locator"]["native_id"] == "LEAN-2"
