"""Retrieval metrics: recall@k and MRR, computed per query over file paths."""


def recall_at_k(retrieved_files: list[str], ground_truth_files: list[str]) -> float:
    """Fraction of `ground_truth_files` present anywhere in `retrieved_files`."""
    if not ground_truth_files:
        return 0.0
    hits = set(retrieved_files) & set(ground_truth_files)
    return len(hits) / len(set(ground_truth_files))


def mrr(retrieved_files: list[str], ground_truth_files: list[str]) -> float:
    """Reciprocal rank of the first ground-truth file found in `retrieved_files` (rank order matters).

    0.0 if none of the ground-truth files appear at all.
    """
    ground_truth_set = set(ground_truth_files)
    for rank, file_path in enumerate(retrieved_files, start=1):
        if file_path in ground_truth_set:
            return 1.0 / rank
    return 0.0
