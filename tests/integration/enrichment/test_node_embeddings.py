"""Node embedding generation (enrichment/node_embeddings.py) against the
Jira fixture connector — real DB session, fake LLM (no live Ollama needed).
Same idempotency/failure-isolation contract as
enrichment/confluence_abstracts.py, generalized across connectors.
"""

from context_fabric.connectors.jira.fixture import JiraFixtureConnector
from context_fabric.domain.errors import NotFound
from context_fabric.enrichment.node_embeddings import enrich_node_embeddings
from context_fabric.enrichment.ollama_client import EnrichmentError
from context_fabric.persistence.repositories.node import NodeRepository
from context_fabric.synchronization import sync_source

_INSTANCE_ID = "jira-acme"
_EMBED_MODEL = "nomic-embed-text"


class FakeOllama:
    def __init__(self, *, fail_for: set[str] | None = None) -> None:
        self.embed_calls: list[str] = []
        self._fail_for = fail_for or set()

    async def embed(self, text: str, *, model: str | None = None) -> list[float]:
        self.embed_calls.append(text)
        if any(marker in text for marker in self._fail_for):
            raise EnrichmentError("simulated embedding failure")
        return [float(len(text) % 7), float(len(text) % 5), 1.0]


async def test_embeds_every_embeddable_kind_and_skips_subtask(db_session):
    # Fixture issues: TALENT-1 Epic, TALENT-2 Story, TALENT-3 Bug,
    # TALENT-4 Sub-task (not in EMBEDDABLE_KINDS), PLAT-1 Task — 4 of 5
    # should get embedded.
    await sync_source(db_session, JiraFixtureConnector(), source_instance_id=_INSTANCE_ID)
    node_repo = NodeRepository(db_session)
    ollama = FakeOllama()

    stats = await enrich_node_embeddings(
        JiraFixtureConnector(),
        node_repo,
        ollama,
        source_instance_id=_INSTANCE_ID,
        embed_model=_EMBED_MODEL,
    )

    assert stats.embeddings_generated == 4
    assert stats.errors == 0

    epic = await node_repo.get_by_technical_identity("jira", _INSTANCE_ID, "TALENT-1")
    assert isinstance(epic.attributes["embedding"], list)
    assert epic.attributes["embedding_model"] == _EMBED_MODEL
    assert epic.attributes["embedding_source_hash"] == epic.content_hash

    subtask = await node_repo.get_by_technical_identity("jira", _INSTANCE_ID, "TALENT-4")
    assert "embedding" not in subtask.attributes


async def test_rerun_without_force_skips_unchanged_nodes(db_session):
    await sync_source(db_session, JiraFixtureConnector(), source_instance_id=_INSTANCE_ID)
    node_repo = NodeRepository(db_session)

    await enrich_node_embeddings(
        JiraFixtureConnector(),
        node_repo,
        FakeOllama(),
        source_instance_id=_INSTANCE_ID,
        embed_model=_EMBED_MODEL,
    )
    second_ollama = FakeOllama()
    stats = await enrich_node_embeddings(
        JiraFixtureConnector(),
        node_repo,
        second_ollama,
        source_instance_id=_INSTANCE_ID,
        embed_model=_EMBED_MODEL,
    )

    assert stats.embeddings_generated == 0
    assert stats.skipped_unchanged == 4
    assert second_ollama.embed_calls == []


async def test_force_regenerates_unchanged_nodes(db_session):
    await sync_source(db_session, JiraFixtureConnector(), source_instance_id=_INSTANCE_ID)
    node_repo = NodeRepository(db_session)

    await enrich_node_embeddings(
        JiraFixtureConnector(),
        node_repo,
        FakeOllama(),
        source_instance_id=_INSTANCE_ID,
        embed_model=_EMBED_MODEL,
    )
    stats = await enrich_node_embeddings(
        JiraFixtureConnector(),
        node_repo,
        FakeOllama(),
        source_instance_id=_INSTANCE_ID,
        embed_model=_EMBED_MODEL,
        force=True,
    )

    assert stats.embeddings_generated == 4
    assert stats.skipped_unchanged == 0


async def test_nodes_not_yet_synced_are_skipped_not_created(db_session):
    node_repo = NodeRepository(db_session)
    stats = await enrich_node_embeddings(
        JiraFixtureConnector(),
        node_repo,
        FakeOllama(),
        source_instance_id=_INSTANCE_ID,
        embed_model=_EMBED_MODEL,
    )

    assert stats.skipped_not_synced == 4
    assert stats.embeddings_generated == 0
    assert (await node_repo.get_by_technical_identity("jira", _INSTANCE_ID, "TALENT-1")) is None


async def test_no_content_available_falls_back_to_name_not_a_hard_failure(db_session):
    """Regression: found live against real Azure DevOps PRs — when
    get_content() raises NotFound (no support for that kind, or the
    vendor genuinely has nothing), the node must still get embedded from
    its name, not be counted as an error. First cut of this fallback
    chain let the NotFound propagate past the name fallback entirely."""

    class NoContentConnector(JiraFixtureConnector):
        async def get_content(self, native_id: str, version: str | None = None):
            raise NotFound(f"no content for native_id={native_id!r}", source_system="jira")

    await sync_source(db_session, JiraFixtureConnector(), source_instance_id=_INSTANCE_ID)
    node_repo = NodeRepository(db_session)
    ollama = FakeOllama()

    stats = await enrich_node_embeddings(
        NoContentConnector(),
        node_repo,
        ollama,
        source_instance_id=_INSTANCE_ID,
        embed_model=_EMBED_MODEL,
    )

    assert stats.errors == 0
    assert stats.embeddings_generated == 4
    # TALENT-1's summary ("SSO Epic") is what got embedded, since
    # get_content is unavailable and description isn't stored on the
    # node for Jira issues (ADR-003 — only the bounded ADO PR case does).
    assert any("SSO Epic" in call for call in ollama.embed_calls)


async def test_a_failed_embedding_is_counted_and_others_still_succeed(db_session):
    await sync_source(db_session, JiraFixtureConnector(), source_instance_id=_INSTANCE_ID)
    node_repo = NodeRepository(db_session)
    # TALENT-3's description mentions "SAML flow work" — fail only for it.
    ollama = FakeOllama(fail_for={"SAML flow work"})

    stats = await enrich_node_embeddings(
        JiraFixtureConnector(),
        node_repo,
        ollama,
        source_instance_id=_INSTANCE_ID,
        embed_model=_EMBED_MODEL,
    )

    assert stats.errors == 1
    assert stats.embeddings_generated == 3
    failed = await node_repo.get_by_technical_identity("jira", _INSTANCE_ID, "TALENT-3")
    assert "embedding" not in failed.attributes
