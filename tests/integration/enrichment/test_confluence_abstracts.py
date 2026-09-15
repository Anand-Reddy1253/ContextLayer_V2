"""Confluence page enrichment (enrichment/confluence_abstracts.py) against
the fixture connector — real DB session, fake LLM (no live Ollama needed).
"""

from context_fabric.connectors.confluence.fixture import ConfluenceFixtureConnector
from context_fabric.enrichment.confluence_abstracts import enrich_confluence_pages
from context_fabric.enrichment.ollama_client import EnrichmentError, LLMAbstractResult
from context_fabric.persistence.repositories.node import NodeRepository
from context_fabric.synchronization import sync_source

_INSTANCE_ID = "confluence-acme"
_EMBED_MODEL = "nomic-embed-text"


class FakeOllama:
    """Same call shape as OllamaClient.generate_abstract/embed,
    deterministic output — no live model call."""

    def __init__(
        self, *, fail_for: set[str] | None = None, fail_embed_for: set[str] | None = None
    ) -> None:
        self.calls: list[str] = []
        self.embed_calls: list[str] = []
        self._fail_for = fail_for or set()
        self._fail_embed_for = fail_embed_for or set()

    async def generate_abstract(self, text: str) -> LLMAbstractResult:
        self.calls.append(text)
        if any(marker in text for marker in self._fail_for):
            raise EnrichmentError("simulated model failure")
        return LLMAbstractResult(abstract=f"Summary of: {text[:30]}", keywords=["sso", "oauth"])

    async def embed(self, text: str, *, model: str | None = None) -> list[float]:
        self.embed_calls.append(text)
        if any(marker in text for marker in self._fail_embed_for):
            raise EnrichmentError("simulated embedding failure")
        # Deterministic, distinct-enough-to-compare vector from the text's
        # own length — no real model needed to prove the wiring works.
        return [float(len(text) % 7), float(len(text) % 5), 1.0]


async def test_enrich_generates_abstracts_and_embeddings_for_every_synced_page(db_session):
    await sync_source(
        db_session, ConfluenceFixtureConnector(), source_instance_id=_INSTANCE_ID
    )
    node_repo = NodeRepository(db_session)
    ollama = FakeOllama()

    stats = await enrich_confluence_pages(
        ConfluenceFixtureConnector(),
        node_repo,
        ollama,
        source_instance_id=_INSTANCE_ID,
        embed_model=_EMBED_MODEL,
    )

    assert stats.pages_scanned == 3
    assert stats.abstracts_generated == 3
    assert stats.embeddings_generated == 3
    assert stats.skipped_unchanged == 0
    assert stats.skipped_not_synced == 0
    assert stats.errors == 0

    page = await node_repo.get_by_technical_identity("confluence", _INSTANCE_ID, "131074")
    assert page is not None
    assert page.attributes["llm_abstract"].startswith("Summary of:")
    assert page.attributes["llm_keywords"] == ["sso", "oauth"]
    assert page.attributes["description_origin"] == "llm"
    assert page.attributes["llm_abstract_source_hash"] == page.content_hash
    assert isinstance(page.attributes["embedding"], list)
    assert len(page.attributes["embedding"]) == 3
    assert all(isinstance(x, float) for x in page.attributes["embedding"])
    assert page.attributes["embedding_model"] == _EMBED_MODEL
    assert page.attributes["embedding_source_hash"] == page.content_hash
    assert page.description is None  # vendor description untouched — there was none


async def test_rerun_without_force_skips_unchanged_pages(db_session):
    await sync_source(
        db_session, ConfluenceFixtureConnector(), source_instance_id=_INSTANCE_ID
    )
    node_repo = NodeRepository(db_session)

    await enrich_confluence_pages(
        ConfluenceFixtureConnector(),
        node_repo,
        FakeOllama(),
        source_instance_id=_INSTANCE_ID,
        embed_model=_EMBED_MODEL,
    )
    second_ollama = FakeOllama()
    stats = await enrich_confluence_pages(
        ConfluenceFixtureConnector(),
        node_repo,
        second_ollama,
        source_instance_id=_INSTANCE_ID,
        embed_model=_EMBED_MODEL,
    )

    assert stats.abstracts_generated == 0
    assert stats.embeddings_generated == 0
    assert stats.skipped_unchanged == 3
    assert second_ollama.calls == []
    assert second_ollama.embed_calls == []


async def test_force_regenerates_unchanged_pages(db_session):
    await sync_source(
        db_session, ConfluenceFixtureConnector(), source_instance_id=_INSTANCE_ID
    )
    node_repo = NodeRepository(db_session)

    await enrich_confluence_pages(
        ConfluenceFixtureConnector(),
        node_repo,
        FakeOllama(),
        source_instance_id=_INSTANCE_ID,
        embed_model=_EMBED_MODEL,
    )
    stats = await enrich_confluence_pages(
        ConfluenceFixtureConnector(),
        node_repo,
        FakeOllama(),
        source_instance_id=_INSTANCE_ID,
        embed_model=_EMBED_MODEL,
        force=True,
    )

    assert stats.abstracts_generated == 3
    assert stats.embeddings_generated == 3
    assert stats.skipped_unchanged == 0


async def test_pages_not_yet_synced_are_skipped_not_created(db_session):
    # No sync_source call at all — every page the walk discovers has no
    # corresponding Node yet.
    node_repo = NodeRepository(db_session)
    stats = await enrich_confluence_pages(
        ConfluenceFixtureConnector(),
        node_repo,
        FakeOllama(),
        source_instance_id=_INSTANCE_ID,
        embed_model=_EMBED_MODEL,
    )

    assert stats.pages_scanned == 3
    assert stats.skipped_not_synced == 3
    assert stats.abstracts_generated == 0
    assert (
        await node_repo.get_by_technical_identity("confluence", _INSTANCE_ID, "131073")
    ) is None


async def test_a_failed_abstract_is_counted_and_others_still_succeed(db_session):
    await sync_source(
        db_session, ConfluenceFixtureConnector(), source_instance_id=_INSTANCE_ID
    )
    node_repo = NodeRepository(db_session)
    # Page 131073's body mentions "SSO epic" — fail generation only for it.
    ollama = FakeOllama(fail_for={"SSO epic"})

    stats = await enrich_confluence_pages(
        ConfluenceFixtureConnector(),
        node_repo,
        ollama,
        source_instance_id=_INSTANCE_ID,
        embed_model=_EMBED_MODEL,
    )

    assert stats.errors == 1
    assert stats.abstracts_generated == 2
    # Embedding is an independent operation — it should still succeed for
    # the same page whose abstract failed.
    assert stats.embeddings_generated == 3
    failed_page = await node_repo.get_by_technical_identity("confluence", _INSTANCE_ID, "131073")
    assert "llm_abstract" not in failed_page.attributes
    assert "embedding" in failed_page.attributes


async def test_a_failed_embedding_does_not_lose_a_successful_abstract(db_session):
    await sync_source(
        db_session, ConfluenceFixtureConnector(), source_instance_id=_INSTANCE_ID
    )
    node_repo = NodeRepository(db_session)
    ollama = FakeOllama(fail_embed_for={"SSO epic"})

    stats = await enrich_confluence_pages(
        ConfluenceFixtureConnector(),
        node_repo,
        ollama,
        source_instance_id=_INSTANCE_ID,
        embed_model=_EMBED_MODEL,
    )

    assert stats.errors == 1
    assert stats.abstracts_generated == 3
    assert stats.embeddings_generated == 2
    page = await node_repo.get_by_technical_identity("confluence", _INSTANCE_ID, "131073")
    assert page.attributes["llm_abstract"].startswith("Summary of:")
    assert "embedding" not in page.attributes


async def test_embedding_backfills_without_regenerating_an_already_correct_abstract(db_session):
    """A page enriched before embeddings existed (llm_abstract_source_hash
    already matches, no embedding yet) should get its embedding backfilled
    on the next run without a second generate_abstract call."""
    await sync_source(
        db_session, ConfluenceFixtureConnector(), source_instance_id=_INSTANCE_ID
    )
    node_repo = NodeRepository(db_session)
    page = await node_repo.get_by_technical_identity("confluence", _INSTANCE_ID, "131073")
    page.attributes = {
        **page.attributes,
        "llm_abstract": "A pre-existing abstract.",
        "llm_keywords": ["preexisting"],
        "description_origin": "llm",
        "llm_abstract_source_hash": page.content_hash,
        "llm_abstract_generated_at": "2026-01-01T00:00:00+00:00",
    }
    await node_repo.update(page)

    ollama = FakeOllama()
    stats = await enrich_confluence_pages(
        ConfluenceFixtureConnector(),
        node_repo,
        ollama,
        source_instance_id=_INSTANCE_ID,
        embed_model=_EMBED_MODEL,
    )

    assert stats.abstracts_generated == 2  # the other two pages only
    assert stats.embeddings_generated == 3  # all three, including this one
    updated = await node_repo.get_by_technical_identity("confluence", _INSTANCE_ID, "131073")
    assert updated.attributes["llm_abstract"] == "A pre-existing abstract."  # untouched
    assert "embedding" in updated.attributes
