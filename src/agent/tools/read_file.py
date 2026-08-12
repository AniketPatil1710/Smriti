"""Tool: read a file, optionally restricted to a line range, from the indexed repo."""

from langchain_core.tools import tool

import config
from src.ingestion.cloner import get_active_repo_root
from src.utils.citations import Citation
from src.utils.logger import get_logger

logger = get_logger(__name__)


@tool(response_format="content_and_artifact")
def read_file(path: str, start_line: int | None = None, end_line: int | None = None) -> tuple[str, list[Citation]]:
    """Read a file from the indexed repository.

    Pass `start_line`/`end_line` (1-indexed, inclusive) to see the full
    context around a chunk returned by semantic_search, or omit both to read
    the whole file. Returns an error string, not an exception, if the path
    doesn't exist or falls outside the repo.
    """
    try:
        repo_root = get_active_repo_root()
    except RuntimeError as e:
        return f"Error: {e}", []

    target = (repo_root / path).resolve()
    repo_root_resolved = repo_root.resolve()
    if target != repo_root_resolved and repo_root_resolved not in target.parents:
        return f"Error: '{path}' is outside the indexed repository", []
    if not target.exists():
        return f"Error: file not found: {path}", []
    if not target.is_file():
        return f"Error: not a file: {path}", []

    try:
        text = target.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError) as e:
        return f"Error: could not read {path}: {e}", []

    lines = text.split("\n")
    line_start = max(1, start_line or 1)
    line_end = min(len(lines), end_line or len(lines))
    text = "\n".join(lines[line_start - 1 : line_end])

    citation = Citation(
        source="code",
        label=f"{path}:{line_start}-{line_end}",
        text=text,
        file_path=path,
        start_line=line_start,
        end_line=line_end,
    )

    output = text
    if len(output) > config.MAX_TOOL_OUTPUT_CHARS:
        output = output[: config.MAX_TOOL_OUTPUT_CHARS] + "\n... (truncated)"
    return output, [citation]
