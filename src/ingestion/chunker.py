"""Language-aware chunking that tracks start/end line numbers through the split.

Python gets AST-aware chunking (ast_chunker.py): each function or class is
its own chunk instead of being cut at an arbitrary character boundary.
Every other language keeps the character splitter, which is still
language-aware at a coarser level (it prefers to break on blank lines and
block keywords over the middle of a line).
"""

from dataclasses import dataclass

from langchain_text_splitters import Language, RecursiveCharacterTextSplitter

from config import CHUNK_OVERLAP, CHUNK_SIZE
from src.ingestion.ast_chunker import chunk_python_ast
from src.ingestion.file_walker import SourceFile
from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class Chunk:
    chunk_id: str  # "<file_path>:<start_line>-<end_line>"
    text: str
    file_path: str
    start_line: int
    end_line: int
    language: str
    repo: str


def chunk_file(
    source_file: SourceFile,
    repo: str,
    chunk_size: int = CHUNK_SIZE,
    chunk_overlap: int = CHUNK_OVERLAP,
) -> list[Chunk]:
    """Split one source file into line-numbered chunks.

    Returns [] if the file can't be decoded as text or is empty — the walk
    already filtered binaries, but a mixed-encoding repo can still slip one
    through, and this must degrade, not abort the ingestion run.
    """
    try:
        full_text = source_file.path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError) as e:
        logger.warning(f"skipping {source_file.relative_path}: could not read as text ({e})")
        return []

    if not full_text.strip():
        return []

    segments = chunk_python_ast(full_text, chunk_size) if source_file.language == "python" else None

    pieces: list[tuple[str, int, int]] = []
    if segments is None:
        pieces.extend(_split_by_characters(full_text, source_file.relative_path, source_file.language, chunk_size, chunk_overlap))
    else:
        for text, start_line, end_line in segments:
            if len(text) <= chunk_size:
                pieces.append((text, start_line, end_line))
            else:
                # A function/class/statement group AST chunking kept whole can
                # still be bigger than chunk_size (a function has no smaller
                # AST-level boundary) — fall back to character splitting just
                # within that piece rather than emitting one oversized chunk.
                pieces.extend(_subdivide(text, start_line, source_file.language, chunk_size, chunk_overlap))

    chunks: list[Chunk] = []
    seen_line_ranges: dict[str, int] = {}
    for text, start_line, end_line in pieces:
        # A single very long line (e.g. a base64 blob) can be split into several
        # chunks that all report the same start/end line — disambiguate so
        # chunk_id, which downstream is used as the Chroma document id, stays unique.
        base_id = f"{source_file.relative_path}:{start_line}-{end_line}"
        occurrence = seen_line_ranges.get(base_id, 0)
        seen_line_ranges[base_id] = occurrence + 1
        chunk_id = base_id if occurrence == 0 else f"{base_id}#{occurrence}"

        chunks.append(
            Chunk(
                chunk_id=chunk_id,
                text=text,
                file_path=source_file.relative_path,
                start_line=start_line,
                end_line=end_line,
                language=source_file.language,
                repo=repo,
            )
        )

    return chunks


def _split_by_characters(
    full_text: str, relative_path: str, language: str, chunk_size: int, chunk_overlap: int
) -> list[tuple[str, int, int]]:
    splitter = _splitter_for(language, chunk_size, chunk_overlap)
    pieces = splitter.split_text(full_text)

    located: list[tuple[str, int, int]] = []
    cursor = 0
    for piece in pieces:
        offset = full_text.find(piece, cursor)
        if offset == -1:
            offset = full_text.find(piece)  # overlap can back up before cursor
        if offset == -1:
            logger.warning(f"could not locate a chunk of {relative_path} in its source text, skipping chunk")
            continue
        cursor = offset
        located.append((piece, _line_number(full_text, offset), _line_number(full_text, offset + len(piece))))
    return located


def _subdivide(
    text: str, base_start_line: int, language: str, chunk_size: int, chunk_overlap: int
) -> list[tuple[str, int, int]]:
    """Character-split one oversized AST segment, translating its relative line numbers back to file line numbers."""
    located = _split_by_characters(text, "<ast segment>", language, chunk_size, chunk_overlap)
    return [(piece, base_start_line - 1 + start, base_start_line - 1 + end) for piece, start, end in located]


def _splitter_for(language: str, chunk_size: int, chunk_overlap: int) -> RecursiveCharacterTextSplitter:
    try:
        lang = Language(language)
    except ValueError:
        return RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    return RecursiveCharacterTextSplitter.from_language(
        language=lang, chunk_size=chunk_size, chunk_overlap=chunk_overlap
    )


def _line_number(text: str, offset: int) -> int:
    """1-indexed line number containing `offset`."""
    return text.count("\n", 0, offset) + 1
