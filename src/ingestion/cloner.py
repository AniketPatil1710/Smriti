"""Clone a public GitHub repo by URL into data/repos/<name>."""

from pathlib import Path
from urllib.parse import urlparse

import git

from config import ACTIVE_REPO_MARKER, REPOS_DIR
from src.utils.logger import get_logger

logger = get_logger(__name__)


class InvalidRepoURLError(ValueError):
    """Raised when a repo URL isn't a usable public GitHub URL."""


def _parse_owner_and_name(url: str) -> tuple[str, str]:
    parsed = urlparse(url)
    if parsed.netloc != "github.com" or not parsed.path.strip("/"):
        raise InvalidRepoURLError(
            f"'{url}' is not a public GitHub repo URL, e.g. https://github.com/<owner>/<repo>"
        )
    parts = parsed.path.strip("/").split("/")
    if len(parts) < 2:
        raise InvalidRepoURLError(f"'{url}' is missing an owner or repo name")
    owner = parts[0]
    name = parts[1][:-4] if parts[1].endswith(".git") else parts[1]
    return owner, name


def repo_name_from_url(url: str) -> str:
    """Derive the local directory name (`<owner>/<repo>` -> `<repo>`) from a GitHub URL."""
    _, name = _parse_owner_and_name(url)
    return name


def repo_full_name_from_url(url: str) -> str:
    """Derive `<owner>/<repo>` from a GitHub URL, as needed by the GitHub API."""
    owner, name = _parse_owner_and_name(url)
    return f"{owner}/{name}"


def clone_repo(url: str) -> Path:
    """Clone `url` into data/repos/<name>. Reuses an existing clone if present."""
    name = repo_name_from_url(url)
    dest = REPOS_DIR / name

    if dest.exists():
        logger.info(f"{name} already cloned at {dest}, reusing")
        return dest

    REPOS_DIR.mkdir(parents=True, exist_ok=True)
    logger.info(f"cloning {url} -> {dest}")
    try:
        git.Repo.clone_from(url, dest)
    except git.GitCommandError as e:
        raise InvalidRepoURLError(f"failed to clone '{url}': {e}") from e

    return dest


def set_active_repo(name: str) -> None:
    """Record which repo's clone corresponds to the current Chroma index."""
    ACTIVE_REPO_MARKER.parent.mkdir(parents=True, exist_ok=True)
    ACTIVE_REPO_MARKER.write_text(name)


def get_active_repo_root() -> Path:
    """Return the local clone path of whichever repo was most recently indexed.

    Reads data/repos/ is not enough on its own — old clones from previous
    ingestion runs can still be sitting there, so the marker written by
    `set_active_repo` is what identifies which one matches the current
    Chroma `code` collection.
    """
    if not ACTIVE_REPO_MARKER.exists():
        raise RuntimeError("No repo has been ingested yet — run `python ingest.py --repo <url>` first.")
    name = ACTIVE_REPO_MARKER.read_text().strip()
    return REPOS_DIR / name
