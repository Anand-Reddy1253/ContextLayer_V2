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
