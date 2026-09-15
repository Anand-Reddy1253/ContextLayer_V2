from uuid import uuid4

from context_fabric.retrieval.semantic import (
    cosine_similarity,
    rank_by_similarity,
    reciprocal_rank_fusion,
)


def test_cosine_similarity_identical_vectors_is_one():
    assert cosine_similarity([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]) == 1.0


def test_cosine_similarity_orthogonal_vectors_is_zero():
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == 0.0


def test_cosine_similarity_opposite_vectors_is_negative_one():
    assert cosine_similarity([1.0, 0.0], [-1.0, 0.0]) == -1.0


def test_cosine_similarity_mismatched_length_is_zero_not_an_error():
    assert cosine_similarity([1.0, 2.0], [1.0, 2.0, 3.0]) == 0.0


def test_cosine_similarity_zero_vector_is_zero_not_an_error():
    assert cosine_similarity([0.0, 0.0], [1.0, 2.0]) == 0.0


def test_rank_by_similarity_orders_best_match_first():
    query = [1.0, 0.0]
    a, b, c = uuid4(), uuid4(), uuid4()
    candidates = [
        (a, [0.0, 1.0]),  # orthogonal
        (b, [1.0, 0.0]),  # identical
        (c, [-1.0, 0.0]),  # opposite
    ]
    # min_similarity=-2 disables the floor for this test — it's checking
    # ordering, not the floor itself (see the dedicated tests below).
    assert rank_by_similarity(query, candidates, min_similarity=-2) == [b, a, c]


def test_rank_by_similarity_excludes_results_below_the_floor():
    query = [1.0, 0.0]
    close, far = uuid4(), uuid4()
    candidates = [
        (close, [0.9, 0.1]),  # cosine ~0.99, a real match
        (far, [0.1, 0.9]),  # cosine ~0.11, noise
    ]
    assert rank_by_similarity(query, candidates) == [close]


def test_rank_by_similarity_returns_empty_when_nothing_clears_the_floor():
    query = [1.0, 0.0]
    candidates = [(uuid4(), [0.0, 1.0])]  # orthogonal — cosine 0.0
    assert rank_by_similarity(query, candidates) == []


def test_reciprocal_rank_fusion_single_ranking_matches_its_own_order():
    a, b = uuid4(), uuid4()
    fused = reciprocal_rank_fusion([[a, b]])
    assert fused[a] > fused[b]


def test_reciprocal_rank_fusion_rewards_agreement_across_rankings():
    a, b = uuid4(), uuid4()
    # a is #2 in one ranking and #1 in another; b is #1 in only one and
    # absent from the other — agreement across both rankings should win.
    fused = reciprocal_rank_fusion([[b, a], [a]])
    assert fused[a] > fused[b]


def test_reciprocal_rank_fusion_node_absent_from_one_ranking_still_scores():
    a, b = uuid4(), uuid4()
    fused = reciprocal_rank_fusion([[a], [b]])
    assert a in fused
    assert b in fused
    assert fused[a] == fused[b]  # both are rank 1 in exactly one list
