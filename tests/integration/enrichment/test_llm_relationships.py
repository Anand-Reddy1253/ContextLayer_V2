"""LLM-inferred relationship extraction (enrichment/llm_relationships.py,
ADR-011) against the fixture connector — real DB session, fake LLM (no
live Ollama needed). Covers: service/reference resolution into real
edges, the content-hash skip gate, page_type scoping, and that every
resulting edge is PROPOSED/LLM_INFERRED and respects a prior human
REJECTED decision (upsert_edge's existing idempotency)."""

from datetime import UTC, datetime

from context_fabric.connectors.confluence.fixture import ConfluenceFixtureConnector
from context_fabric.domain.enums import EdgeOrigin, EdgeState, EdgeType
from context_fabric.enrichment.llm_relationships import extract_llm_relationships
from context_fabric.enrichment.ollama_client import (
    DocumentReference,
    LLMRelationshipExtractionResult,
)
from context_fabric.persistence.repositories.edge import EdgeRepository
from context_fabric.persistence.repositories.node import NodeRepository
from context_fabric.synchronization import sync_source
from context_fabric.synchronization.idempotency import upsert_edge
from tests.integration.persistence.factories import make_node

_INSTANCE_ID = "confluence-acme"
_MODEL_NAME = "llama3.2:1b"

_EMPTY_RESULT = LLMRelationshipExtractionResult(services=[], references=[])


class FakeOllama:
    """Same call shape as OllamaClient.extract_document_relationships —
    returns a canned result keyed by a distinctive substring of the text
    passed in, deterministic, no live model call."""

    def __init__(self, responses: dict[str, LLMRelationshipExtractionResult] | None = None) -> None:
        self.calls: list[str] = []
        self._responses = responses or {}

    async def extract_document_relationships(
        self, text: str, *, known_services: list[str]
    ) -> LLMRelationshipExtractionResult:
        self.calls.append(text)
        for marker, result in self._responses.items():
            if marker in text:
                return result
        return _EMPTY_RESULT


async def _make_service_node(node_repo: NodeRepository, name: str):
    now = datetime.now(UTC)
    node = make_node(
        now,
        kind="SERVICE",
        name=name,
        path=f"acme.test.{name.replace('-', '_')}",
    )
    return await node_repo.create(node)


async def _mark_classified(node_repo: NodeRepository, native_id: str, page_type: str) -> None:
    """Simulates Tier 3's deterministic classification having already run
    for this page — the real classify_page() only recognizes a handful of
    fixture bodies (ADR-014's structured macro), so tests that need a
    *second* classified document set the attribute directly, the same way
    test_confluence_abstracts.py's backfill test pre-seeds attributes."""
    node = await node_repo.get_by_technical_identity("confluence", _INSTANCE_ID, native_id)
    assert node is not None
    node.attributes = {**node.attributes, "page_type": page_type}
    await node_repo.update(node)


async def test_proposes_service_and_reference_edges_for_classified_documents(db_session):
    await sync_source(db_session, ConfluenceFixtureConnector(), source_instance_id=_INSTANCE_ID)
    node_repo = NodeRepository(db_session)
    edge_repo = EdgeRepository(db_session)

    # 131076 (ADR-014) is classified by the real Tier 3 logic already;
    # 131074 (SSO Design Doc) is marked classified here to give the
    # reference hint below something to resolve against.
    await _mark_classified(node_repo, "131074", "PRD")
    service_node = await _make_service_node(node_repo, "settlement-service")

    ollama = FakeOllama(
        {
            "event sourcing": LLMRelationshipExtractionResult(
                services=["settlement-service"],
                references=[
                    DocumentReference(
                        document_hint="the SSO design documentation", relationship="decides_on"
                    )
                ],
            )
        }
    )

    stats = await extract_llm_relationships(
        ConfluenceFixtureConnector(),
        node_repo,
        edge_repo,
        ollama,
        source_instance_id=_INSTANCE_ID,
        model_name=_MODEL_NAME,
    )

    assert stats.documents_classified == 2
    assert stats.services_proposed == 1
    assert stats.relationships_proposed == 1
    assert stats.unmatched_references == 0
    assert stats.errors == 0

    adr_node = await node_repo.get_by_technical_identity("confluence", _INSTANCE_ID, "131076")
    sso_node = await node_repo.get_by_technical_identity("confluence", _INSTANCE_ID, "131074")

    service_edges = await edge_repo.list_from(adr_node.id)
    related = next(e for e in service_edges if e.type == EdgeType.RELATED_TO)
    assert related.dst_id == service_node.id
    assert related.origin is EdgeOrigin.LLM_INFERRED
    assert related.state is EdgeState.PROPOSED
    assert related.attributes["extracted_by"] == "llm"
    assert related.attributes["model"] == _MODEL_NAME
    assert "settlement-service" in related.attributes["rationale"]

    decides = next(e for e in service_edges if e.type == EdgeType.DECIDES_ON)
    assert decides.dst_id == sso_node.id
    assert decides.origin is EdgeOrigin.LLM_INFERRED
    assert decides.state is EdgeState.PROPOSED
    assert decides.attributes["rationale"] == "the SSO design documentation"

    assert adr_node.attributes["llm_relationships_source_hash"] == adr_node.content_hash


async def test_unresolved_reference_hint_is_dropped_and_counted(db_session):
    await sync_source(db_session, ConfluenceFixtureConnector(), source_instance_id=_INSTANCE_ID)
    node_repo = NodeRepository(db_session)
    edge_repo = EdgeRepository(db_session)

    ollama = FakeOllama(
        {
            "event sourcing": LLMRelationshipExtractionResult(
                services=[],
                references=[
                    DocumentReference(
                        document_hint="some completely unrelated forgotten memo",
                        relationship="caused_by",
                    )
                ],
            )
        }
    )

    stats = await extract_llm_relationships(
        ConfluenceFixtureConnector(),
        node_repo,
        edge_repo,
        ollama,
        source_instance_id=_INSTANCE_ID,
        model_name=_MODEL_NAME,
    )

    assert stats.unmatched_references == 1
    assert stats.relationships_proposed == 0


async def test_unknown_service_name_from_a_stale_client_is_not_resolved(db_session):
    """OllamaClient.extract_document_relationships already drops any
    service name outside the closed vocabulary it was given — this
    proves the resolution step is *also* safe if a service name somehow
    arrives that has no matching real node (defense in depth, not
    reachable through the real client today)."""
    await sync_source(db_session, ConfluenceFixtureConnector(), source_instance_id=_INSTANCE_ID)
    node_repo = NodeRepository(db_session)
    edge_repo = EdgeRepository(db_session)

    ollama = FakeOllama(
        {
            "event sourcing": LLMRelationshipExtractionResult(
                services=["a-service-that-does-not-exist"], references=[]
            )
        }
    )

    stats = await extract_llm_relationships(
        ConfluenceFixtureConnector(),
        node_repo,
        edge_repo,
        ollama,
        source_instance_id=_INSTANCE_ID,
        model_name=_MODEL_NAME,
    )

    assert stats.services_proposed == 0


async def test_only_classified_documents_are_scanned(db_session):
    await sync_source(db_session, ConfluenceFixtureConnector(), source_instance_id=_INSTANCE_ID)
    node_repo = NodeRepository(db_session)
    edge_repo = EdgeRepository(db_session)
    ollama = FakeOllama()

    await extract_llm_relationships(
        ConfluenceFixtureConnector(),
        node_repo,
        edge_repo,
        ollama,
        source_instance_id=_INSTANCE_ID,
        model_name=_MODEL_NAME,
    )

    # Only 131076 (ADR-014) is classified by the real Tier 3 logic in this
    # fixture set — "SSO Design Doc", "Identity Squad Home", and
    # "Platform Engineering Home" must never reach the model.
    assert len(ollama.calls) == 1
    assert "event sourcing" in ollama.calls[0]


async def test_rerun_without_force_skips_unchanged_documents(db_session):
    await sync_source(db_session, ConfluenceFixtureConnector(), source_instance_id=_INSTANCE_ID)
    node_repo = NodeRepository(db_session)
    edge_repo = EdgeRepository(db_session)

    await extract_llm_relationships(
        ConfluenceFixtureConnector(),
        node_repo,
        edge_repo,
        FakeOllama(),
        source_instance_id=_INSTANCE_ID,
        model_name=_MODEL_NAME,
    )
    second_ollama = FakeOllama()
    stats = await extract_llm_relationships(
        ConfluenceFixtureConnector(),
        node_repo,
        edge_repo,
        second_ollama,
        source_instance_id=_INSTANCE_ID,
        model_name=_MODEL_NAME,
    )

    assert stats.skipped_unchanged == 1
    assert second_ollama.calls == []


async def test_force_reruns_unchanged_documents(db_session):
    await sync_source(db_session, ConfluenceFixtureConnector(), source_instance_id=_INSTANCE_ID)
    node_repo = NodeRepository(db_session)
    edge_repo = EdgeRepository(db_session)

    await extract_llm_relationships(
        ConfluenceFixtureConnector(),
        node_repo,
        edge_repo,
        FakeOllama(),
        source_instance_id=_INSTANCE_ID,
        model_name=_MODEL_NAME,
    )
    stats = await extract_llm_relationships(
        ConfluenceFixtureConnector(),
        node_repo,
        edge_repo,
        FakeOllama(),
        source_instance_id=_INSTANCE_ID,
        model_name=_MODEL_NAME,
        force=True,
    )

    assert stats.skipped_unchanged == 0
    assert stats.documents_classified == 1


async def test_a_prior_human_rejection_is_not_reproposed(db_session):
    """A human REJECTED this exact (src, dst, type, origin) edge before —
    upsert_edge's identity check finds it regardless of state and skips
    recreating it, same idempotency every other extracted edge relies on."""
    await sync_source(db_session, ConfluenceFixtureConnector(), source_instance_id=_INSTANCE_ID)
    node_repo = NodeRepository(db_session)
    edge_repo = EdgeRepository(db_session)
    service_node = await _make_service_node(node_repo, "settlement-service")
    adr_node = await node_repo.get_by_technical_identity("confluence", _INSTANCE_ID, "131076")

    now = datetime.now(UTC)
    from context_fabric.domain.edge import Edge

    rejected = Edge(
        src_id=adr_node.id,
        dst_id=service_node.id,
        type=EdgeType.RELATED_TO,
        origin=EdgeOrigin.LLM_INFERRED,
        state=EdgeState.REJECTED,
        first_seen_at=now,
        last_seen_at=now,
    )
    assert await upsert_edge(edge_repo, rejected)

    ollama = FakeOllama(
        {
            "event sourcing": LLMRelationshipExtractionResult(
                services=["settlement-service"], references=[]
            )
        }
    )
    stats = await extract_llm_relationships(
        ConfluenceFixtureConnector(),
        node_repo,
        edge_repo,
        ollama,
        source_instance_id=_INSTANCE_ID,
        model_name=_MODEL_NAME,
    )

    assert stats.services_proposed == 0
    edges = await edge_repo.list_from(adr_node.id)
    related = [e for e in edges if e.type == EdgeType.RELATED_TO and e.dst_id == service_node.id]
    assert len(related) == 1
    assert related[0].state is EdgeState.REJECTED
