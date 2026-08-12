"""Reciprocal Rank Fusion of ranked ID lists."""

import config


def reciprocal_rank_fusion(rankings: list[list[str]], k: int = config.RRF_K) -> list[str]:
    """Fuse multiple rankings of doc IDs into one, by Reciprocal Rank Fusion.

    Each ranking is a list of IDs, best first. score(d) = sum over rankings of
    1 / (k + rank). Rank-based, so scores from different methods (cosine
    similarity, BM25) never need to be normalized against each other. Returns
    fused IDs, best first.
    """
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, doc_id in enumerate(ranking, start=1):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank)
    return sorted(scores, key=lambda doc_id: scores[doc_id], reverse=True)
