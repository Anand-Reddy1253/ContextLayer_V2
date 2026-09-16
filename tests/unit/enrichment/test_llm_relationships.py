"""Unit coverage for enrichment/llm_relationships.py's deterministic
fuzzy-title resolution — the "no second LLM call" half of ADR-011.
"""

from uuid import uuid4

from context_fabric.enrichment.llm_relationships import _resolve_document_hint


def test_resolves_a_close_paraphrase_of_a_real_title():
    doc_id = uuid4()
    candidates = {
        doc_id: "ADR-014 Move settlement to event sourcing",
        uuid4(): "Platform Engineering Home",
    }
    assert _resolve_document_hint("the settlement event sourcing decision", candidates) == doc_id


def test_tolerates_small_typos_via_the_shared_fuzzy_threshold():
    doc_id = uuid4()
    candidates = {doc_id: "SSO Design Doc"}
    # "Desgin" — one transposition, same discipline as catalog.py's own
    # fuzzy tier (_FUZZY_WORD_THRESHOLD = 0.75). "documentation" is the
    # hint's third significant word (_MIN_HINT_WORDS) — it matches nothing
    # in the title itself, only "sso"/"desgin" do, which is exactly the
    # 2-of-3 _MIN_MATCHED_WORDS floor this is meant to exercise.
    assert _resolve_document_hint("the SSO Desgin documentation page", candidates) == doc_id


def test_returns_none_for_an_unrelated_hint():
    candidates = {uuid4(): "ADR-014 Move settlement to event sourcing"}
    assert _resolve_document_hint("the Q3 hiring plan", candidates) is None


def test_returns_none_for_an_empty_hint():
    candidates = {uuid4(): "ADR-014 Move settlement to event sourcing"}
    assert _resolve_document_hint("", candidates) is None


def test_returns_none_when_no_candidates_exist():
    assert _resolve_document_hint("the settlement decision", {}) is None


def test_a_short_generic_hint_is_never_resolved_even_on_a_lucky_fuzzy_hit():
    """Found live against a real Confluence org: the hint "Decides on the
    solution." (2 significant words after stopwords: "decides",
    "solution") matched "ADR-0018 ... Schema Evolution ..." only because
    SequenceMatcher("solution", "evolution").ratio() = 0.82 — a
    coincidental shared suffix, not a real reference. A hint this short
    must never resolve, regardless of how well a single word happens to
    fuzzy-match."""
    candidates = {uuid4(): "ADR-0018: Schema Evolution for the Talentflow Datastore"}
    assert _resolve_document_hint("Decides on the solution.", candidates) is None


def test_picks_the_best_of_several_similar_titles():
    settlement_id = uuid4()
    identity_id = uuid4()
    candidates = {
        settlement_id: "ADR-014 Move settlement to event sourcing",
        identity_id: "ADR-009 Identity token rotation",
    }
    assert _resolve_document_hint("the settlement event sourcing proposal", candidates) == (
        settlement_id
    )
