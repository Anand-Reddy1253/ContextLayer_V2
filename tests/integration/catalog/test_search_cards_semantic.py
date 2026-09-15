"""`semantic=true` on GET /catalog/search-cards (api/routes/catalog.py) —
opt-in cosine-similarity ranking merged with the existing lexical
`_score_match` ranking via reciprocal rank fusion (retrieval/semantic.py).
Real DB session, Ollama's `/api/embed` mocked via respx (no live model
needed) — this is testing the wiring and the "additive, never a
replacement" contract, not embedding quality.
"""

from datetime import UTC, datetime

import httpx
import respx

from context_fabric.api.routes.catalog import search_cards
from context_fabric.domain.enums import Layer
from context_fabric.domain.node import Node
from context_fabric.persistence.repositories.node import NodeRepository

_OLLAMA_BASE_URL = "http://localhost:11434"


async def _make_node(node_repo: NodeRepository, *, name: str, native_id: str, embedding=None):
    now = datetime.now(UTC)
    attributes = {"embedding": embedding} if embedding is not None else {}
    return await node_repo.create(
        Node(
            layer=Layer.TECHNICAL,
            kind="PAGE",
            name=name,
            source_system="confluence",
            source_instance_id="conf-acme",
            native_id=native_id,
            path=f"space.{native_id}",
            attributes=attributes,
            first_seen_at=now,
            last_seen_at=now,
            created_at=now,
            updated_at=now,
        )
    )


async def test_semantic_false_by_default_matches_lexical_only(db_session):
    node_repo = NodeRepository(db_session)
    await _make_node(node_repo, name="SSO Login Flow", native_id="1")
    # No lexical hit for "sso" in name/description, but a stored embedding —
    # must NOT appear when semantic isn't requested.
    await _make_node(
        node_repo, name="Unrelated Onboarding Guide", native_id="2", embedding=[1.0, 0.0, 0.0]
    )

    cards = await search_cards(q="sso", session=db_session, limit=100)

    names = {c["node"]["name"] for c in cards}
    assert "SSO Login Flow" in names
    assert "Unrelated Onboarding Guide" not in names


@respx.mock
async def test_semantic_true_surfaces_a_node_with_no_lexical_match(db_session):
    node_repo = NodeRepository(db_session)
    await _make_node(node_repo, name="SSO Login Flow", native_id="1")
    await _make_node(
        node_repo, name="Unrelated Onboarding Guide", native_id="2", embedding=[1.0, 0.0, 0.0]
    )

    respx.post(f"{_OLLAMA_BASE_URL}/api/embed").mock(
        return_value=httpx.Response(200, json={"embeddings": [[1.0, 0.0, 0.0]]})
    )

    cards = await search_cards(q="sso", session=db_session, semantic=True, limit=100)

    names = {c["node"]["name"] for c in cards}
    assert "SSO Login Flow" in names
    assert "Unrelated Onboarding Guide" in names


@respx.mock
async def test_semantic_true_falls_back_to_lexical_when_ollama_unreachable(db_session):
    node_repo = NodeRepository(db_session)
    await _make_node(node_repo, name="SSO Login Flow", native_id="1")
    await _make_node(
        node_repo, name="Unrelated Onboarding Guide", native_id="2", embedding=[1.0, 0.0, 0.0]
    )

    respx.post(f"{_OLLAMA_BASE_URL}/api/embed").mock(side_effect=httpx.ConnectError("refused"))

    cards = await search_cards(q="sso", session=db_session, semantic=True, limit=100)

    names = {c["node"]["name"] for c in cards}
    assert "SSO Login Flow" in names
    assert "Unrelated Onboarding Guide" not in names
