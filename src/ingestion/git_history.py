"""git log + GitHub PR API -> HistoryRecord objects, joined on merge commit SHA."""

import os
import time
from dataclasses import dataclass
from pathlib import Path

import git
from github import Auth, Github
from github.GithubException import BadCredentialsException, GithubException

import config
from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class HistoryRecord:
    record_id: str  # "pr:<number>" or "commit:<short_sha>"
    text: str
    type: str  # "commit" | "pr"
    sha: str
    pr_number: int | None
    files_touched: list[str]
    date: str  # ISO date


def encode_files_touched(files_touched: list[str]) -> str:
    """Chroma metadata can't hold lists — encode as `|a|b|c|`, substring-matched at query time."""
    d = config.FILES_TOUCHED_DELIMITER
    return d + d.join(files_touched) + d


def decode_files_touched(encoded: str) -> list[str]:
    d = config.FILES_TOUCHED_DELIMITER
    return [f for f in encoded.split(d) if f]


def build_history_records(repo_root: Path, repo_full_name: str) -> list[HistoryRecord]:
    """Walk local git history, enriching commits that merged a PR with its title/body.

    Commits with no matching PR (direct pushes, older history, etc.) still
    become plain "commit" records from their own message.
    """
    pr_by_sha = _fetch_merged_prs(repo_full_name)

    local_repo = git.Repo(repo_root)
    records: list[HistoryRecord] = []
    for commit in local_repo.iter_commits(max_count=config.MAX_COMMITS):
        try:
            files_touched = list(commit.stats.files.keys())
        except (git.GitCommandError, ValueError) as e:
            logger.warning(f"could not get file stats for commit {commit.hexsha[:7]}: {e}")
            continue
        if not files_touched:
            continue

        date = commit.committed_datetime.date().isoformat()
        pr = pr_by_sha.get(commit.hexsha)

        if pr is not None:
            text = f"{pr['title']}\n\n{pr['body'] or ''}".strip()
            records.append(
                HistoryRecord(
                    record_id=f"pr:{pr['number']}",
                    text=text,
                    type="pr",
                    sha=commit.hexsha,
                    pr_number=pr["number"],
                    files_touched=files_touched,
                    date=date,
                )
            )
        else:
            message = commit.message.strip()
            if not message:
                continue
            records.append(
                HistoryRecord(
                    record_id=f"commit:{commit.hexsha[:7]}",
                    text=message,
                    type="commit",
                    sha=commit.hexsha,
                    pr_number=None,
                    files_touched=files_touched,
                    date=date,
                )
            )

    pr_count = sum(1 for r in records if r.type == "pr")
    logger.info(f"built {len(records)} history records ({pr_count} pr, {len(records) - pr_count} commit)")
    return records


def _fetch_merged_prs(repo_full_name: str) -> dict[str, dict]:
    """Return {merge_commit_sha: {number, title, body}} for recently merged PRs.

    Uses the PR *list* endpoint only — title/body/merge_commit_sha are present
    there directly, so this costs no extra per-PR API calls (verified: 50 PRs
    with title/body/merge_commit_sha accessed consumed 0 rate-limit units
    beyond the list call itself).
    """
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise RuntimeError("GITHUB_TOKEN is not set — required to build the history index")

    last_error: Exception | None = None
    for attempt in range(1, config.GITHUB_MAX_RETRIES + 1):
        try:
            gh = Github(auth=Auth.Token(token), per_page=100)  # default 30 triples the page count
            repo = gh.get_repo(repo_full_name)

            pr_by_sha: dict[str, dict] = {}
            scanned = 0
            for pr in repo.get_pulls(state="closed", sort="created", direction="desc"):
                scanned += 1
                if scanned > config.HISTORY_PR_SCAN_LIMIT:
                    break
                if pr.merged_at is not None and pr.merge_commit_sha is not None:
                    pr_by_sha[pr.merge_commit_sha] = {
                        "number": pr.number,
                        "title": pr.title,
                        "body": pr.body,
                    }

            logger.info(f"scanned {scanned} closed PRs, {len(pr_by_sha)} merged with a resolvable merge commit")
            return pr_by_sha
        except BadCredentialsException as e:
            raise RuntimeError(f"GitHub authentication failed — check GITHUB_TOKEN in .env: {e}") from e
        except GithubException as e:
            last_error = e
            wait = 2**attempt
            logger.warning(
                f"GitHub API call failed ({type(e).__name__}), "
                f"retrying in {wait}s (attempt {attempt}/{config.GITHUB_MAX_RETRIES})"
            )
            time.sleep(wait)

    raise RuntimeError(f"GitHub API call failed after {config.GITHUB_MAX_RETRIES} attempts: {last_error}") from last_error
