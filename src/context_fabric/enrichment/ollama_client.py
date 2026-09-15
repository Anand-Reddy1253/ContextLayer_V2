"""Local LLM client (Ollama) for generating bounded search abstracts +
keywords — ADR-010's "selective LLM-generated abstracts", local model,
generated offline, never on `get_context_pack`'s path.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import TypeVar

import httpx
import tenacity
from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

R = TypeVar("R")

_MAX_ABSTRACT_CHARS = 500
_MAX_KEYWORDS = 8
_MAX_KEYWORD_CHARS = 40

_PROMPT_TEMPLATE = """You are summarizing an internal documentation page for a search index.
Read the page text below and respond with ONLY a JSON object of this exact shape:
{{"abstract": "<one or two sentence summary, plain text, no markdown>", \
"keywords": ["<short keyword or phrase>", ...]}}

Rules:
- abstract must be under {max_abstract_chars} characters.
- keywords: {max_keywords} at most, each under {max_keyword_chars} characters, \
lowercase, no duplicates.
- Do not include any text outside the JSON object.

Page text:
\"\"\"
{text}
\"\"\"
"""


class EnrichmentError(Exception):
    """Ollama unreachable, or its response didn't parse into a valid
    LLMAbstractResult. Callers (enrichment/confluence_abstracts.py) catch
    this per-page — one bad/unavailable model response must never abort a
    whole enrichment run, and a failed page is simply skipped, never
    written with garbage."""


class LLMAbstractResult(BaseModel):
    """Bounded, hard-capped, plain-text derived fields (ADR-010) — never a
    stored body, always regenerable from source."""

    model_config = ConfigDict(extra="forbid")

    abstract: str
    keywords: list[str] = []

    @field_validator("abstract")
    @classmethod
    def _bound_abstract(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("abstract must not be empty")
        return v[:_MAX_ABSTRACT_CHARS]

    @field_validator("keywords")
    @classmethod
    def _bound_keywords(cls, v: list[str]) -> list[str]:
        seen: set[str] = set()
        bounded: list[str] = []
        for kw in v:
            kw = kw.strip().lower()[:_MAX_KEYWORD_CHARS]
            if kw and kw not in seen:
                seen.add(kw)
                bounded.append(kw)
            if len(bounded) >= _MAX_KEYWORDS:
                break
        return bounded


def _is_retryable(exc: BaseException) -> bool:
    return isinstance(exc, httpx.TransportError | httpx.TimeoutException)


class OllamaClient:
    """Thin wrapper over Ollama's `/api/generate` and `/api/embed`
    (localhost REST API, no auth) — same bounded-retry shape as
    connectors/base.py::LiveConnectorBase.call_with_retry, but this isn't a
    SourceConnector (no vendor data, no error-category taxonomy to map
    onto)."""

    def __init__(
        self,
        base_url: str,
        model: str,
        *,
        # 180s, not a more typical 30-60s — measured live against
        # llama3.2:1b on CPU-only hardware: a ~7200-char page took ~200s
        # to generate. Input is now capped at 3000 chars
        # (confluence_abstracts.py), but this stays generous as a safety
        # margin rather than tuned to exactly that case.
        timeout: httpx.Timeout = httpx.Timeout(180.0, connect=5.0),
        max_attempts: int = 3,
    ) -> None:
        self._client = httpx.AsyncClient(base_url=base_url, timeout=timeout)
        self._model = model
        self._max_attempts = max_attempts

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _call_with_retry(self, func: Callable[[], Awaitable[R]]) -> R:
        retryer = tenacity.AsyncRetrying(
            retry=tenacity.retry_if_exception(_is_retryable),
            wait=tenacity.wait_random_exponential(multiplier=0.5, max=10.0),
            stop=tenacity.stop_after_attempt(self._max_attempts),
            reraise=True,
        )
        async for attempt in retryer:
            with attempt:
                return await func()
        raise AssertionError("unreachable: tenacity always returns or raises")

    async def generate_abstract(self, text: str) -> LLMAbstractResult:
        if not text.strip():
            raise EnrichmentError("no text to summarize")

        prompt = _PROMPT_TEMPLATE.format(
            max_abstract_chars=_MAX_ABSTRACT_CHARS,
            max_keywords=_MAX_KEYWORDS,
            max_keyword_chars=_MAX_KEYWORD_CHARS,
            text=text,
        )

        try:
            response = await self._call_with_retry(
                lambda: self._client.post(
                    "/api/generate",
                    json={
                        "model": self._model,
                        "prompt": prompt,
                        "format": "json",
                        "stream": False,
                    },
                )
            )
        except (httpx.TransportError, httpx.TimeoutException) as exc:
            raise EnrichmentError(
                f"could not reach Ollama at {self._client.base_url}: {exc}"
            ) from exc

        if response.status_code != 200:
            raise EnrichmentError(f"Ollama returned {response.status_code}: {response.text[:500]}")

        try:
            payload = response.json()
            raw_result = payload["response"]
        except (json.JSONDecodeError, KeyError) as exc:
            raise EnrichmentError(f"unexpected Ollama response shape: {exc}") from exc

        try:
            return LLMAbstractResult.model_validate_json(raw_result)
        except (ValidationError, json.JSONDecodeError) as exc:
            raise EnrichmentError(
                f"model output did not match the expected {{abstract, keywords}} shape: {exc}"
            ) from exc

    async def embed(self, text: str, *, model: str | None = None) -> list[float]:
        """A dense vector for `text`, via Ollama's `/api/embed` (distinct
        from `/api/generate` — a different model family, single forward
        pass, no decoding, so it's fast even where a generation call on
        the same hardware isn't). `model` defaults to this client's own
        `self._model`, but the call site (confluence_abstracts.py) passes
        the *embedding* model explicitly — the same OllamaClient instance
        serves both `generate_abstract`'s completion model and this
        embedding model, since they're never the same model."""
        if not text.strip():
            raise EnrichmentError("no text to embed")

        try:
            response = await self._call_with_retry(
                lambda: self._client.post(
                    "/api/embed",
                    json={"model": model or self._model, "input": text},
                )
            )
        except (httpx.TransportError, httpx.TimeoutException) as exc:
            raise EnrichmentError(
                f"could not reach Ollama at {self._client.base_url}: {exc}"
            ) from exc

        if response.status_code != 200:
            raise EnrichmentError(f"Ollama returned {response.status_code}: {response.text[:500]}")

        try:
            payload = response.json()
            embeddings = payload["embeddings"]
            vector = embeddings[0]
        except (json.JSONDecodeError, KeyError, IndexError) as exc:
            raise EnrichmentError(f"unexpected Ollama embed response shape: {exc}") from exc

        if not isinstance(vector, list) or not vector or not all(
            isinstance(x, int | float) for x in vector
        ):
            raise EnrichmentError("embed response did not contain a numeric vector")
        return [float(x) for x in vector]
