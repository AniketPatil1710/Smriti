"""Tool: semantic search over the indexed codebase."""

from langchain_core.tools import tool

import config
from src.retrieval.retriever import retrieve
from src.utils.citations import Citation, citation_from_chunk
from src.utils.logger import get_logger

logger = get_logger(__name__)


@tool(response_format="content_and_artifact")
def semantic_search(query: str) -> tuple[str, list[Citation]]:
    """Search the codebase for chunks semantically related to `query`.

    Returns each match as a `[file_path:start_line-end_line]` citation
    followed by a text preview. Use read_file on a citation to see the full
    surrounding context before answering.
    """
    try:
        results = retrieve(query, optimize=True)
    except Exception as e:
        logger.warning(f"semantic_search failed for {query!r}: {e}")
        return f"Error: search failed: {e}", []

    if not results:
        return "No relevant code found for this query.", []

    # Full chunk text, not a short fixed-length preview: a chunk can contain
    # more than one function, and truncating early can hide the very match
    # that made this chunk rank #1 (found via a real case — a chunk starting
    # with one function's body but containing a second, more relevant
    # function further down, past where a 300-char preview cut off). The
    # overall MAX_TOOL_OUTPUT_CHARS cap below still applies, so lower-ranked
    # results are what gets sacrificed if space runs out, not the top one.
    blocks = [f"[{r.file_path}:{r.start_line}-{r.end_line}]\n{r.text}" for r in results]

    output = "\n\n".join(blocks)
    if len(output) > config.MAX_TOOL_OUTPUT_CHARS:
        output = output[: config.MAX_TOOL_OUTPUT_CHARS] + "\n... (truncated)"

    citations = [citation_from_chunk(r) for r in results]
    return output, citations
