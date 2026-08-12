"""CLI entry point for indexing a repo: python ingest.py --repo <url>"""

import argparse

import config
from src.indexing.bm25_index import build_bm25_index
from src.indexing.embedder import estimate_cost_usd
from src.indexing.vector_store import rebuild_code_collection, rebuild_history_collection
from src.ingestion.chunker import chunk_file
from src.ingestion.cloner import clone_repo, repo_full_name_from_url, set_active_repo
from src.ingestion.file_walker import language_breakdown, walk_repo
from src.ingestion.git_history import build_history_records
from src.utils.logger import get_logger

logger = get_logger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Index a public GitHub repo into Smriti.")
    parser.add_argument("--repo", required=True, help="GitHub repo URL, e.g. https://github.com/fastapi/fastapi")
    args = parser.parse_args()

    repo_root = clone_repo(args.repo)
    files = walk_repo(repo_root)

    print(f"\n{len(files)} source files found in {repo_root.name}")
    print("\nPer-language breakdown:")
    for language, count in language_breakdown(files).items():
        print(f"  {language:<12} {count}")

    print("\nChunking...")
    chunks = []
    for source_file in files:
        chunks.extend(chunk_file(source_file, repo=repo_root.name))
    print(f"{len(chunks)} chunks from {len(files)} files")

    if not _confirm_cost([c.text for c in chunks], "code"):
        print("Aborted.")
        return

    print("Embedding + indexing code into Chroma...")
    rebuild_code_collection(chunks)
    print(f"Indexed {len(chunks)} chunks into the 'code' collection.")

    build_bm25_index(chunks)
    print(f"Built BM25 index over {len(chunks)} chunks.")

    print("\nBuilding history index...")
    history_records = build_history_records(repo_root, repo_full_name_from_url(args.repo))
    print(f"{len(history_records)} history records "
          f"({sum(1 for r in history_records if r.type == 'pr')} pr, "
          f"{sum(1 for r in history_records if r.type == 'commit')} commit)")

    if not _confirm_cost([r.text for r in history_records], "history"):
        print("Skipped history index.")
    else:
        print("Embedding + indexing history into Chroma...")
        rebuild_history_collection(history_records)
        print(f"Indexed {len(history_records)} records into the 'history' collection.")

    set_active_repo(repo_root.name)


def _confirm_cost(texts: list[str], label: str) -> bool:
    """Print the estimated embedding cost for `texts`; prompt for confirmation above the threshold."""
    cost = estimate_cost_usd(texts)
    if cost > config.COST_CONFIRMATION_THRESHOLD_USD:
        answer = input(f"Estimated {label} embedding cost: ${cost:.2f}. Continue? [y/N]: ").strip().lower()
        return answer == "y"
    if cost > 0:
        print(f"Estimated {label} embedding cost: ${cost:.4f}")
    return True


if __name__ == "__main__":
    main()
