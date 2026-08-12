"""Tool: list one directory level of the indexed repo, with sub-directories collapsed to counts."""

from langchain_core.tools import tool

import config
from src.ingestion.cloner import get_active_repo_root
from src.utils.logger import get_logger

logger = get_logger(__name__)


@tool
def list_files(directory: str = "") -> str:
    """List the immediate contents of a directory in the indexed repo.

    Pass an empty string for the repo root. Sub-directories are shown as a
    file count rather than expanded, so this stays bounded on large repos —
    use it to orient, then read_file or semantic_search to go deeper.
    """
    try:
        repo_root = get_active_repo_root()
    except RuntimeError as e:
        return f"Error: {e}"

    target = (repo_root / directory).resolve() if directory else repo_root.resolve()
    repo_root_resolved = repo_root.resolve()
    if target != repo_root_resolved and repo_root_resolved not in target.parents:
        return f"Error: '{directory}' is outside the indexed repository"
    if not target.exists():
        return f"Error: directory not found: {directory}"
    if not target.is_dir():
        return f"Error: not a directory: {directory}"

    lines = []
    for entry in sorted(target.iterdir(), key=lambda p: p.name):
        if entry.name in config.SKIP_DIR_NAMES:
            continue
        if entry.is_dir():
            file_count = sum(1 for f in entry.rglob("*") if f.is_file())
            lines.append(f"{entry.name}/  ({file_count} files)")
        else:
            lines.append(entry.name)

    output = "\n".join(lines) if lines else "(empty)"
    if len(output) > config.MAX_TOOL_OUTPUT_CHARS:
        output = output[: config.MAX_TOOL_OUTPUT_CHARS] + "\n... (truncated)"
    return output
