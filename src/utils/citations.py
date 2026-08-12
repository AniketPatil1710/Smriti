"""Chunk / history-record metadata -> structured citation objects.

Citations are built from tool artifacts — the retrieval metadata itself —
never parsed or retyped from the model's own prose. The model can mis-state
a number when writing its answer (observed once in Phase 6: a correct
`routing.py:2255-2280` retrieval became "line 1255" in the final text); a
citation built directly from what a tool actually returned can't drift like
that.
"""

from dataclasses import dataclass

from src.retrieval.retriever import RetrievedChunk, RetrievedHistoryRecord


@dataclass(frozen=True)
class Citation:
    source: str  # "code" | "history"
    label: str  # short display label, e.g. "tokens.py:42-78" or "#4821"
    text: str  # full cited text, for UI expansion — not truncated for the LLM
    file_path: str | None = None
    start_line: int | None = None
    end_line: int | None = None
    pr_number: int | None = None
    sha: str | None = None


def citation_from_chunk(chunk: RetrievedChunk) -> Citation:
    return Citation(
        source="code",
        label=f"{chunk.file_path}:{chunk.start_line}-{chunk.end_line}",
        text=chunk.text,
        file_path=chunk.file_path,
        start_line=chunk.start_line,
        end_line=chunk.end_line,
    )


def citation_from_history_record(record: RetrievedHistoryRecord) -> Citation:
    label = f"#{record.pr_number}" if record.pr_number is not None else record.sha[:7]
    return Citation(
        source="history",
        label=label,
        text=record.text,
        pr_number=record.pr_number,
        sha=record.sha,
    )


def dedupe(citations: list[Citation]) -> list[Citation]:
    """Remove exact-duplicate citations (same source + label), preserving first-seen order."""
    seen: set[tuple[str, str]] = set()
    result = []
    for c in citations:
        key = (c.source, c.label)
        if key in seen:
            continue
        seen.add(key)
        result.append(c)
    return result
