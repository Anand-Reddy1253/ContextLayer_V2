"""Local LLM client (Ollama) for generating bounded search abstracts +
keywords — ADR-010's "selective LLM-generated abstracts" — and, since
ADR-011, one-document-at-a-time relationship extraction (never a pairwise
comparison between two documents). Local model, generated offline, never
on `get_context_pack`'s path.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Literal, TypeVar

import httpx
import tenacity
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, ValidationError, field_validator

R = TypeVar("R")

_MAX_ABSTRACT_CHARS = 500
_MAX_KEYWORDS = 8
_MAX_KEYWORD_CHARS = 40

_MAX_SERVICES = 10
_MAX_SERVICE_NAME_CHARS = 100
_MAX_REFERENCES = 10
_MAX_HINT_CHARS = 200

RelationshipHint = Literal["supersedes", "superseded_by", "caused_by", "decides_on"]

_RELATIONSHIP_PROMPT_TEMPLATE = """\
You are analyzing one internal document (an ADR, postmortem, PRD, or
meeting notes) — not comparing it to anything else. Extract two things:
which of a fixed list of services/products it concerns, and which other
documents it explicitly references, with how.

Known services/products — choose only from this list, copied exactly as
written; do not invent or guess a name that isn't here:
{services_list}

Read the document text below and respond with ONLY a JSON object of this
exact shape:
{{"services": ["<name copied exactly from the list above>", ...], \
"references": [{{"document_hint": "<short description of the other \
document, in your own words, based only on what this text says about \
it>", "relationship": "<one of: supersedes, superseded_by, caused_by, \
decides_on>"}}, ...]}}

Rules:
- services: only names that appear verbatim in the known list above.
  Empty list if none clearly apply.
- references: only include another document if this text explicitly
  states a relationship to it (e.g. "supersedes...", "caused by the
  incident described in...", "this decision was made in the meeting...").
  Do not guess or infer a weak or possible association — leave it out if
  you're not sure.
- document_hint must be under {max_hint_chars} characters.
- relationship must be exactly one of: supersedes, superseded_by,
  caused_by, decides_on.
- Do not include any text outside the JSON object.

Document text:
\"\"\"
{text}
\"\"\"
"""

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


class DocumentReference(BaseModel):
    """One other document this document explicitly references, and the
    relationship the model stated (ADR-011). `document_hint` is resolved
    to a real node later, deterministically (fuzzy title matching —
    enrichment/llm_relationships.py) — never by asking the model to
    compare against a second document directly."""

    model_config = ConfigDict(extra="forbid")

    # llama3.2:1b, live against real pages, inconsistently emits "document"
    # instead of the prompted "document_hint" key on some calls — accepting
    # either avoids losing an otherwise-valid reference over a naming
    # quirk the prompt already asks it not to make.
    document_hint: str = Field(validation_alias=AliasChoices("document_hint", "document"))
    relationship: RelationshipHint

    @field_validator("document_hint")
    @classmethod
    def _bound_hint(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("document_hint must not be empty")
        return v[:_MAX_HINT_CHARS]


class LLMRelationshipExtractionResult(BaseModel):
    """Bounded, validated output of one single-document extraction call
    (ADR-011 — never a pairwise comparison). `services` is filtered
    against the caller's own known-vocabulary list by
    OllamaClient.extract_document_relationships itself (a Pydantic
    validator has no access to that external context), not here."""

    model_config = ConfigDict(extra="forbid")

    services: list[str] = []
    references: list[DocumentReference] = []

    @field_validator("services")
    @classmethod
    def _bound_services(cls, v: list[str]) -> list[str]:
        seen: set[str] = set()
        bounded: list[str] = []
        for name in v:
            name = name.strip()[:_MAX_SERVICE_NAME_CHARS]
            if name and name not in seen:
                seen.add(name)
                bounded.append(name)
            if len(bounded) >= _MAX_SERVICES:
                break
        return bounded

    @field_validator("references")
    @classmethod
    def _bound_references(cls, v: list[DocumentReference]) -> list[DocumentReference]:
        return v[:_MAX_REFERENCES]


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

    async def _generate_json(self, prompt: str) -> str:
        """The shared call+envelope-unwrap step behind both
        generate_abstract and extract_document_relationships — Ollama's
        `/api/generate` response wraps the model's own JSON string inside
        `{"response": "..."}`; this returns that inner string, still
        unparsed, for the caller's own Pydantic model to validate."""
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
            return str(payload["response"])
        except (json.JSONDecodeError, KeyError) as exc:
            raise EnrichmentError(f"unexpected Ollama response shape: {exc}") from exc

    async def generate_abstract(self, text: str) -> LLMAbstractResult:
        if not text.strip():
            raise EnrichmentError("no text to summarize")

        prompt = _PROMPT_TEMPLATE.format(
            max_abstract_chars=_MAX_ABSTRACT_CHARS,
            max_keywords=_MAX_KEYWORDS,
            max_keyword_chars=_MAX_KEYWORD_CHARS,
            text=text,
        )
        raw_result = await self._generate_json(prompt)

        try:
            return LLMAbstractResult.model_validate_json(raw_result)
        except (ValidationError, json.JSONDecodeError) as exc:
            raise EnrichmentError(
                f"model output did not match the expected {{abstract, keywords}} shape: {exc}"
            ) from exc

    async def extract_document_relationships(
        self, text: str, *, known_services: list[str]
    ) -> LLMRelationshipExtractionResult:
        """One document, one call (ADR-011) — never a pairwise comparison.
        `known_services` is the closed vocabulary the model may choose
        from for `services`; anything it returns outside that list is
        dropped here before the caller ever sees it, regardless of
        whether the model followed the prompt's instruction."""
        if not text.strip():
            raise EnrichmentError("no text to analyze")

        services_list = "\n".join(f"- {s}" for s in known_services) or "(none)"
        prompt = _RELATIONSHIP_PROMPT_TEMPLATE.format(
            services_list=services_list,
            max_hint_chars=_MAX_HINT_CHARS,
            text=text,
        )
        raw_result = await self._generate_json(prompt)

        try:
            raw_obj = json.loads(raw_result)
        except json.JSONDecodeError as exc:
            raise EnrichmentError(f"model output was not valid JSON: {exc}") from exc
        if not isinstance(raw_obj, dict):
            raise EnrichmentError("model output was not a JSON object")

        services_raw = raw_obj.get("services", [])
        references_raw = raw_obj.get("references", [])
        if not isinstance(services_raw, list) or not isinstance(references_raw, list):
            raise EnrichmentError(
                "model output did not match the expected {services, references} shape"
            )

        # Each reference is validated on its own, not as one all-or-nothing
        # list — a single malformed entry (an unexpected key, a relationship
        # outside the closed set) must not cost every *other*, otherwise-
        # valid reference the model found for this document. Same "log and
        # drop, don't fail the whole call" spirit as an unresolved hint
        # downstream (llm_relationships.py).
        references: list[DocumentReference] = []
        for item in references_raw:
            try:
                references.append(DocumentReference.model_validate(item))
            except ValidationError:
                continue

        try:
            result = LLMRelationshipExtractionResult(services=services_raw, references=references)
        except ValidationError as exc:
            raise EnrichmentError(
                "model output did not match the expected "
                f"{{services, references}} shape: {exc}"
            ) from exc

        known_set = set(known_services)
        result.services = [s for s in result.services if s in known_set]
        return result

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
