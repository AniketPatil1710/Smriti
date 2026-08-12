"""recall@k and MRR feed the project's headline result directly — worth pinning down."""

from eval.metrics import mrr, recall_at_k


def test_recall_all_ground_truth_present():
    assert recall_at_k(["a", "b", "c"], ["a", "b"]) == 1.0


def test_recall_partial_match():
    assert recall_at_k(["a", "x", "y"], ["a", "b"]) == 0.5


def test_recall_no_match():
    assert recall_at_k(["x", "y"], ["a", "b"]) == 0.0


def test_recall_duplicates_in_retrieved_dont_inflate_score():
    assert recall_at_k(["a", "a", "a"], ["a", "b"]) == 0.5


def test_recall_empty_ground_truth_is_zero_not_division_error():
    assert recall_at_k(["a", "b"], []) == 0.0


def test_mrr_first_position_hit():
    assert mrr(["a", "b", "c"], ["a"]) == 1.0


def test_mrr_third_position_hit():
    assert mrr(["x", "y", "a"], ["a"]) == 1.0 / 3


def test_mrr_uses_earliest_of_multiple_ground_truth_files():
    assert mrr(["x", "b", "a"], ["a", "b"]) == 1.0 / 2  # "b" at rank 2 beats "a" at rank 3


def test_mrr_no_hit_is_zero():
    assert mrr(["x", "y", "z"], ["a"]) == 0.0
