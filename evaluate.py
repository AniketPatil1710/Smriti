"""CLI: python evaluate.py --config <dense|bm25|hybrid|hybrid_history|all>

Retrieval only — bypasses the agent entirely, since retrieval is what's being
measured and this way it's deterministic and fast (Architecture.md §5).
"""

import argparse
import json

import config
from eval.metrics import mrr, recall_at_k
from src.retrieval.hybrid import reciprocal_rank_fusion
from src.retrieval.query_optimizer import optimize_query
from src.retrieval.retriever import retrieve, search_history
from src.utils.logger import get_logger

logger = get_logger(__name__)

CONFIGS = [
    "dense",
    "bm25",
    "hybrid",
    "hybrid_history",
    "hybrid_history_optimized",
    "hybrid_history_optimized_reranked",
]


def load_eval_set() -> list[dict]:
    if not config.EVAL_SET_PATH.exists():
        raise RuntimeError(f"No eval set found at {config.EVAL_SET_PATH} — run eval/build_eval_set.py first.")
    with config.EVAL_SET_PATH.open() as f:
        return json.load(f)


def retrieved_files_for(query: str, config_name: str, exclude_pr: int | None = None) -> list[str]:
    """Ranked file-path list for one query under one config, best first."""
    if config_name in ("dense", "bm25", "hybrid"):
        chunks = retrieve(query, top_k=config.TOP_K, mode=config_name)
        return [c.file_path for c in chunks]

    if config_name in ("hybrid_history", "hybrid_history_optimized", "hybrid_history_optimized_reranked"):
        optimize = config_name != "hybrid_history"
        rerank = config_name == "hybrid_history_optimized_reranked"
        code_chunks = retrieve(query, top_k=config.TOP_K, mode="hybrid", optimize=optimize, rerank=rerank)
        code_files = [c.file_path for c in code_chunks]
        search_query = optimize_query(query) if optimize else query
        history_records = search_history(search_query, top_k=config.TOP_K)
        if exclude_pr is not None:
            # leakage guard: an eval query IS that PR's own body — without this,
            # semantic history search would trivially find itself
            history_records = [r for r in history_records if r.pr_number != exclude_pr]
        history_files = [f for r in history_records for f in r.files_touched]
        fused = reciprocal_rank_fusion([code_files, history_files])
        return fused[: config.TOP_K]

    raise ValueError(f"unknown eval config: {config_name!r} (expected one of {CONFIGS})")


def run_config(config_name: str, eval_set: list[dict]) -> dict:
    """Retrieval-only evaluation of one config against the full eval set."""
    recalls = []
    mrrs = []
    for item in eval_set:
        retrieved = retrieved_files_for(item["query"], config_name, exclude_pr=item.get("pr_number"))
        recalls.append(recall_at_k(retrieved, item["ground_truth_files"]))
        mrrs.append(mrr(retrieved, item["ground_truth_files"]))

    return {
        "config": config_name,
        "recall_at_5": sum(recalls) / len(recalls),
        "mrr": sum(mrrs) / len(mrrs),
        "n": len(eval_set),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate retrieval configs against the eval set.")
    parser.add_argument("--config", required=True, choices=[*CONFIGS, "all"])
    args = parser.parse_args()

    eval_set = load_eval_set()
    print(f"Loaded {len(eval_set)} eval items from {config.EVAL_SET_PATH}")
    config.EVAL_RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    configs_to_run = CONFIGS if args.config == "all" else [args.config]
    results = []
    for config_name in configs_to_run:
        print(f"\nRunning config: {config_name}...")
        result = run_config(config_name, eval_set)
        results.append(result)

        with (config.EVAL_RESULTS_DIR / f"{config_name}.json").open("w") as f:
            json.dump(result, f, indent=2)
        print(f"  recall@5={result['recall_at_5']:.3f}  mrr={result['mrr']:.3f}  (n={result['n']})")

    if len(results) > 1:
        print("\n" + "=" * 42)
        print(f"{'config':<16}{'recall@5':>13}{'mrr':>13}")
        for r in results:
            print(f"{r['config']:<16}{r['recall_at_5']:>13.3f}{r['mrr']:>13.3f}")

        with (config.EVAL_RESULTS_DIR / "comparison.json").open("w") as f:
            json.dump(results, f, indent=2)


if __name__ == "__main__":
    main()
