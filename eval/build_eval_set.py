"""CLI: python -m eval.build_eval_set --repo <url>

Mines merged PRs into {query, ground_truth_files} eval items: the PR body is
treated as a stand-in for a developer's request, the files it touched are
the ground truth for "did retrieval find the right files."
"""

import argparse
import json
import os
import time

from github import Auth, Github
from github.GithubException import BadCredentialsException, GithubException

import config
from src.ingestion.cloner import repo_full_name_from_url
from src.utils.logger import get_logger

logger = get_logger(__name__)


_AUTOMATION_MARKERS = ("created automatically", "generated automatically")


def build_eval_set(repo_full_name: str) -> list[dict]:
    """Scan merged PRs for ones usable as eval items: human-authored, description \
    over EVAL_MIN_DESCRIPTION_CHARS, touching EVAL_MIN_FILES_TOUCHED..EVAL_MAX_FILES_TOUCHED files.

    Filters out two kinds of noise beyond the bot-account check: PRs that
    self-declare as automated (a scheduled translation-sync job, still
    opened under a human-flagged account) and PRs whose title exactly
    repeats an already-accepted item's (a recurring scheduled PR — e.g. a
    "update contributors data" job — with near-zero query signal). Found via
    direct inspection of the first build: 33/146 items were auto-generated
    translation syncs, 4 more were a byte-identical recurring bot PR.
    """
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise RuntimeError("GITHUB_TOKEN is not set — required to build the eval set")

    gh = Github(auth=Auth.Token(token), per_page=100)
    repo = _get_repo_with_retry(gh, repo_full_name)

    items: list[dict] = []
    seen_titles: set[str] = set()
    scanned = 0
    skipped_bot = 0
    skipped_short_desc = 0
    skipped_file_count = 0
    skipped_automated = 0
    skipped_duplicate_title = 0

    for pr in repo.get_pulls(state="closed", sort="created", direction="desc"):
        scanned += 1
        if scanned > config.EVAL_PR_SCAN_LIMIT or len(items) >= config.EVAL_TARGET_SIZE:
            break
        if pr.merged_at is None:
            continue
        if pr.user.type == "Bot":
            skipped_bot += 1
            continue
        if pr.title in seen_titles:
            skipped_duplicate_title += 1
            continue
        body = (pr.body or "").strip()
        if any(marker in body.lower() for marker in _AUTOMATION_MARKERS):
            skipped_automated += 1
            continue
        if len(body) <= config.EVAL_MIN_DESCRIPTION_CHARS:
            skipped_short_desc += 1
            continue

        files = _get_files_with_retry(pr)
        if not (config.EVAL_MIN_FILES_TOUCHED <= len(files) <= config.EVAL_MAX_FILES_TOUCHED):
            skipped_file_count += 1
            continue

        items.append(
            {
                "query": body,
                "ground_truth_files": files,
                "pr_number": pr.number,
                "source": "merged_pr",
            }
        )
        seen_titles.add(pr.title)

    logger.info(
        f"scanned {scanned} closed PRs -> {len(items)} eval items "
        f"(skipped: {skipped_bot} bot, {skipped_automated} self-declared automated, "
        f"{skipped_duplicate_title} duplicate title, {skipped_short_desc} short description, "
        f"{skipped_file_count} file count)"
    )
    return items


def _get_repo_with_retry(gh: Github, repo_full_name: str):
    last_error: Exception | None = None
    for attempt in range(1, config.GITHUB_MAX_RETRIES + 1):
        try:
            return gh.get_repo(repo_full_name)
        except BadCredentialsException as e:
            raise RuntimeError(f"GitHub authentication failed — check GITHUB_TOKEN in .env: {e}") from e
        except GithubException as e:
            last_error = e
            wait = 2**attempt
            logger.warning(f"GitHub call failed ({type(e).__name__}), retrying in {wait}s")
            time.sleep(wait)
    raise RuntimeError(f"GitHub call failed after {config.GITHUB_MAX_RETRIES} attempts: {last_error}") from last_error


def _get_files_with_retry(pr) -> list[str]:
    """Filenames changed in `pr`. A dedicated API call per PR — GitHub never includes \
    the file list on list/get-PR responses."""
    last_error: Exception | None = None
    for attempt in range(1, config.GITHUB_MAX_RETRIES + 1):
        try:
            return [f.filename for f in pr.get_files()]
        except BadCredentialsException as e:
            raise RuntimeError(f"GitHub authentication failed — check GITHUB_TOKEN in .env: {e}") from e
        except GithubException as e:
            last_error = e
            wait = 2**attempt
            logger.warning(f"GitHub call failed ({type(e).__name__}) fetching files for PR #{pr.number}, retrying in {wait}s")
            time.sleep(wait)
    raise RuntimeError(f"GitHub call failed after {config.GITHUB_MAX_RETRIES} attempts: {last_error}") from last_error


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the retrieval eval set from merged PRs.")
    parser.add_argument("--repo", required=True, help="GitHub repo URL, e.g. https://github.com/fastapi/fastapi")
    args = parser.parse_args()

    items = build_eval_set(repo_full_name_from_url(args.repo))

    config.EVAL_SET_PATH.parent.mkdir(parents=True, exist_ok=True)
    with config.EVAL_SET_PATH.open("w") as f:
        json.dump(items, f, indent=2)

    print(f"\n{len(items)} eval items written to {config.EVAL_SET_PATH}")
    print(f"Exit criterion (>= {config.EVAL_MIN_MERGED_PRS}): {'PASS' if len(items) >= config.EVAL_MIN_MERGED_PRS else 'FAIL'}")

    print("\nSample (first 5):")
    for item in items[:5]:
        print(f"  PR #{item['pr_number']}: {item['query'][:80].replace(chr(10), ' ')!r}")
        print(f"    ground_truth_files: {item['ground_truth_files']}")


if __name__ == "__main__":
    main()
