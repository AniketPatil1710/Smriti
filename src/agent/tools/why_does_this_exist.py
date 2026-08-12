"""Tool: explain why a file exists or changed, using the commit/PR history that touched it."""

from langchain_core.tools import tool

import config
from src.retrieval.retriever import get_history_by_file
from src.utils.citations import Citation, citation_from_history_record
from src.utils.logger import get_logger

logger = get_logger(__name__)


@tool(response_format="content_and_artifact")
def why_does_this_exist(file_path: str) -> tuple[str, list[Citation]]:
    """Explain why a file exists or changed, using commit messages and PR descriptions that touched it.

    Returns the most recent history records touching `file_path`, most recent
    first, each labeled with its PR number or commit SHA and date.
    """
    try:
        records = get_history_by_file(file_path)
    except Exception as e:
        logger.warning(f"why_does_this_exist failed for {file_path!r}: {e}")
        return f"Error: history search failed: {e}", []

    if not records:
        return f"No commit or PR history found touching {file_path}.", []

    blocks = []
    for r in records:
        citation_label = f"#{r.pr_number}" if r.pr_number is not None else r.sha[:7]
        preview = r.text if len(r.text) <= 400 else r.text[:400] + "..."
        blocks.append(f"[{citation_label} · {r.date}]\n{preview}")

    output = "\n\n".join(blocks)
    if len(output) > config.MAX_TOOL_OUTPUT_CHARS:
        output = output[: config.MAX_TOOL_OUTPUT_CHARS] + "\n... (truncated)"

    citations = [citation_from_history_record(r) for r in records]
    return output, citations
