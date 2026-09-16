import httpx
import pytest
import respx

from context_fabric.enrichment.ollama_client import EnrichmentError, OllamaClient

_BASE_URL = "http://localhost:11434"


@respx.mock
async def test_generate_abstract_parses_valid_response():
    respx.post(f"{_BASE_URL}/api/generate").mock(
        return_value=httpx.Response(
            200,
            json={
                "response": '{"abstract": "A short summary.", "keywords": ["sso", "oauth"]}'
            },
        )
    )
    client = OllamaClient(_BASE_URL, "llama3.2:1b")
    result = await client.generate_abstract("some page text")
    assert result.abstract == "A short summary."
    assert result.keywords == ["sso", "oauth"]
    await client.aclose()


@respx.mock
async def test_generate_abstract_bounds_oversized_fields():
    respx.post(f"{_BASE_URL}/api/generate").mock(
        return_value=httpx.Response(
            200,
            json={
                "response": (
                    '{"abstract": "' + ("x" * 900) + '", '
                    '"keywords": ' + str([f"kw{i}" for i in range(20)]).replace("'", '"') + "}"
                )
            },
        )
    )
    client = OllamaClient(_BASE_URL, "llama3.2:1b")
    result = await client.generate_abstract("some page text")
    assert len(result.abstract) == 500
    assert len(result.keywords) == 8
    await client.aclose()


@respx.mock
async def test_generate_abstract_raises_on_malformed_json():
    respx.post(f"{_BASE_URL}/api/generate").mock(
        return_value=httpx.Response(200, json={"response": "not json at all"})
    )
    client = OllamaClient(_BASE_URL, "llama3.2:1b")
    with pytest.raises(EnrichmentError):
        await client.generate_abstract("some page text")
    await client.aclose()


@respx.mock
async def test_generate_abstract_raises_on_missing_abstract_field():
    respx.post(f"{_BASE_URL}/api/generate").mock(
        return_value=httpx.Response(200, json={"response": '{"keywords": ["sso"]}'})
    )
    client = OllamaClient(_BASE_URL, "llama3.2:1b")
    with pytest.raises(EnrichmentError):
        await client.generate_abstract("some page text")
    await client.aclose()


@respx.mock
async def test_generate_abstract_raises_when_ollama_unreachable():
    respx.post(f"{_BASE_URL}/api/generate").mock(side_effect=httpx.ConnectError("refused"))
    client = OllamaClient(_BASE_URL, "llama3.2:1b", max_attempts=1)
    with pytest.raises(EnrichmentError):
        await client.generate_abstract("some page text")
    await client.aclose()


async def test_generate_abstract_rejects_empty_text():
    client = OllamaClient(_BASE_URL, "llama3.2:1b")
    with pytest.raises(EnrichmentError):
        await client.generate_abstract("   ")
    await client.aclose()


@respx.mock
async def test_embed_parses_valid_response():
    respx.post(f"{_BASE_URL}/api/embed").mock(
        return_value=httpx.Response(200, json={"embeddings": [[0.1, 0.2, 0.3]]})
    )
    client = OllamaClient(_BASE_URL, "llama3.2:1b")
    vector = await client.embed("some page text", model="nomic-embed-text")
    assert vector == [0.1, 0.2, 0.3]
    await client.aclose()


@respx.mock
async def test_embed_raises_on_missing_embeddings_field():
    respx.post(f"{_BASE_URL}/api/embed").mock(return_value=httpx.Response(200, json={}))
    client = OllamaClient(_BASE_URL, "llama3.2:1b")
    with pytest.raises(EnrichmentError):
        await client.embed("some page text")
    await client.aclose()


@respx.mock
async def test_embed_raises_on_empty_embeddings_list():
    respx.post(f"{_BASE_URL}/api/embed").mock(
        return_value=httpx.Response(200, json={"embeddings": []})
    )
    client = OllamaClient(_BASE_URL, "llama3.2:1b")
    with pytest.raises(EnrichmentError):
        await client.embed("some page text")
    await client.aclose()


@respx.mock
async def test_embed_raises_on_non_numeric_vector():
    respx.post(f"{_BASE_URL}/api/embed").mock(
        return_value=httpx.Response(200, json={"embeddings": [["not", "numbers"]]})
    )
    client = OllamaClient(_BASE_URL, "llama3.2:1b")
    with pytest.raises(EnrichmentError):
        await client.embed("some page text")
    await client.aclose()


@respx.mock
async def test_embed_raises_when_ollama_unreachable():
    respx.post(f"{_BASE_URL}/api/embed").mock(side_effect=httpx.ConnectError("refused"))
    client = OllamaClient(_BASE_URL, "llama3.2:1b", max_attempts=1)
    with pytest.raises(EnrichmentError):
        await client.embed("some page text")
    await client.aclose()


async def test_embed_rejects_empty_text():
    client = OllamaClient(_BASE_URL, "llama3.2:1b")
    with pytest.raises(EnrichmentError):
        await client.embed("   ")
    await client.aclose()


@respx.mock
async def test_extract_document_relationships_parses_valid_response():
    respx.post(f"{_BASE_URL}/api/generate").mock(
        return_value=httpx.Response(
            200,
            json={
                "response": (
                    '{"services": ["settlement"], '
                    '"references": [{"document_hint": "the June proposal", '
                    '"relationship": "supersedes"}]}'
                )
            },
        )
    )
    client = OllamaClient(_BASE_URL, "llama3.2:1b")
    result = await client.extract_document_relationships(
        "some doc text", known_services=["settlement", "payments-api"]
    )
    assert result.services == ["settlement"]
    assert len(result.references) == 1
    assert result.references[0].document_hint == "the June proposal"
    assert result.references[0].relationship == "supersedes"
    await client.aclose()


@respx.mock
async def test_extract_document_relationships_drops_hallucinated_services():
    """A service name the model returns that isn't in the closed
    vocabulary it was given must never survive — ADR-011's hallucination
    guard, applied post-hoc since a Pydantic validator has no access to
    the caller's known_services list."""
    respx.post(f"{_BASE_URL}/api/generate").mock(
        return_value=httpx.Response(
            200,
            json={
                "response": '{"services": ["settlement", "made-up-service"], "references": []}'
            },
        )
    )
    client = OllamaClient(_BASE_URL, "llama3.2:1b")
    result = await client.extract_document_relationships(
        "some doc text", known_services=["settlement", "payments-api"]
    )
    assert result.services == ["settlement"]
    await client.aclose()


@respx.mock
async def test_extract_document_relationships_drops_one_invalid_reference_not_the_whole_call():
    """A reference with a relationship outside the closed Literal set is
    invalid on its own — but each reference is validated individually
    (not as one all-or-nothing list), so a single bad entry is dropped
    and every other, otherwise-valid reference from the same call still
    survives. Found live: llama3.2:1b occasionally emits an out-of-set
    relationship or an extra key on one reference among several good
    ones; failing the whole call would silently lose real, correct
    proposals alongside the bad one."""
    respx.post(f"{_BASE_URL}/api/generate").mock(
        return_value=httpx.Response(
            200,
            json={
                "response": (
                    '{"services": [], "references": ['
                    '{"document_hint": "the good one", "relationship": "caused_by"}, '
                    '{"document_hint": "x", "relationship": "unrelated_to"}'
                    "]}"
                )
            },
        )
    )
    client = OllamaClient(_BASE_URL, "llama3.2:1b")
    result = await client.extract_document_relationships("some doc text", known_services=[])
    assert len(result.references) == 1
    assert result.references[0].document_hint == "the good one"
    await client.aclose()


@respx.mock
async def test_extract_document_relationships_accepts_document_key_alias():
    """llama3.2:1b, observed live against real pages, sometimes emits
    "document" instead of the prompted "document_hint" key — both must
    resolve to the same field rather than losing the reference."""
    respx.post(f"{_BASE_URL}/api/generate").mock(
        return_value=httpx.Response(
            200,
            json={
                "response": (
                    '{"services": [], "references": [{"document": "the June proposal", '
                    '"relationship": "supersedes"}]}'
                )
            },
        )
    )
    client = OllamaClient(_BASE_URL, "llama3.2:1b")
    result = await client.extract_document_relationships("some doc text", known_services=[])
    assert len(result.references) == 1
    assert result.references[0].document_hint == "the June proposal"
    await client.aclose()


@respx.mock
async def test_extract_document_relationships_raises_when_every_reference_is_malformed():
    """references is present but every entry fails validation — an empty
    references list after per-item filtering is a legitimate, valid
    result (not an error); this only checks that a non-list/non-dict
    top-level shape still raises, since that's not recoverable per-item."""
    respx.post(f"{_BASE_URL}/api/generate").mock(
        return_value=httpx.Response(200, json={"response": '{"services": [], "references": "oops"}'})
    )
    client = OllamaClient(_BASE_URL, "llama3.2:1b")
    with pytest.raises(EnrichmentError):
        await client.extract_document_relationships("some doc text", known_services=[])
    await client.aclose()


@respx.mock
async def test_extract_document_relationships_bounds_oversized_lists():
    services = [f"service-{i}" for i in range(20)]
    payload_services = str(services).replace("'", '"')
    references = [
        {"document_hint": f"doc {i}", "relationship": "caused_by"} for i in range(20)
    ]
    payload_references = str(references).replace("'", '"')
    respx.post(f"{_BASE_URL}/api/generate").mock(
        return_value=httpx.Response(
            200,
            json={
                "response": (
                    f'{{"services": {payload_services}, "references": {payload_references}}}'
                )
            },
        )
    )
    client = OllamaClient(_BASE_URL, "llama3.2:1b")
    result = await client.extract_document_relationships("some doc text", known_services=services)
    assert len(result.services) == 10
    assert len(result.references) == 10
    await client.aclose()


async def test_extract_document_relationships_rejects_empty_text():
    client = OllamaClient(_BASE_URL, "llama3.2:1b")
    with pytest.raises(EnrichmentError):
        await client.extract_document_relationships("   ", known_services=[])
    await client.aclose()
