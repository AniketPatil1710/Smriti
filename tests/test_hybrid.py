"""RRF must produce the correct fused ordering — mandatory per Rules.md rule 21."""

from src.retrieval.hybrid import reciprocal_rank_fusion


def test_matches_hand_computed_scores():
    dense = ["x", "y", "z"]
    bm25 = ["y", "z", "x"]
    k = 60

    expected_scores = {
        "x": 1 / (k + 1) + 1 / (k + 3),
        "y": 1 / (k + 2) + 1 / (k + 1),
        "z": 1 / (k + 3) + 1 / (k + 2),
    }
    expected_order = sorted(expected_scores, key=lambda d: expected_scores[d], reverse=True)

    assert reciprocal_rank_fusion([dense, bm25], k=k) == expected_order


def test_top_of_both_rankings_beats_tail_of_both():
    dense = ["a", "b", "c", "d"]
    bm25 = ["b", "a", "d", "c"]

    fused = reciprocal_rank_fusion([dense, bm25])

    assert set(fused[:2]) == {"a", "b"}
    assert set(fused[2:]) == {"c", "d"}


def test_doc_missing_from_one_ranking_is_still_included():
    dense = ["a", "b"]
    bm25 = ["c"]  # e.g. an exact symbol match dense retrieval missed entirely

    fused = reciprocal_rank_fusion([dense, bm25])

    assert "c" in fused


def test_rank_one_in_every_ranking_wins():
    dense = ["a", "b", "c"]
    bm25 = ["a", "c", "b"]

    fused = reciprocal_rank_fusion([dense, bm25])

    assert fused[0] == "a"


def test_single_ranking_is_returned_unchanged():
    ranking = ["a", "b", "c"]
    assert reciprocal_rank_fusion([ranking]) == ranking


def test_empty_input_returns_empty():
    assert reciprocal_rank_fusion([]) == []
    assert reciprocal_rank_fusion([[], []]) == []


def test_k_controls_how_much_appearing_in_both_rankings_matters():
    # "in_both" is rank 3 in both rankings; "solo_first" is rank 1 in one
    # ranking and absent from the other. A large k (dampened) favors
    # consistency across rankings; a small k lets a single rank-1 dominate.
    ranking_a = ["solo_first", "x", "in_both"]
    ranking_b = ["y", "z", "in_both"]

    fused_k60 = reciprocal_rank_fusion([ranking_a, ranking_b], k=60)
    assert fused_k60.index("in_both") < fused_k60.index("solo_first")

    fused_k_small = reciprocal_rank_fusion([ranking_a, ranking_b], k=0.5)
    assert fused_k_small.index("solo_first") < fused_k_small.index("in_both")
