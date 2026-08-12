"""Language-aware chunking that tracks start/end line numbers through the split."""

from dataclasses import dataclass

from langchain_text_splitters import Language, RecursiveCharacterTextSplitter

from config import CHUNK_OVERLAP, CHUNK_SIZE
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

    splitter = _splitter_for(source_file.language, chunk_size, chunk_overlap)
    pieces = splitter.split_text(full_text)

    chunks: list[Chunk] = []
    seen_line_ranges: dict[str, int] = {}
    cursor = 0
    for piece in pieces:
        offset = full_text.find(piece, cursor)
        if offset == -1:
            offset = full_text.find(piece)  # overlap can back up before cursor
        if offset == -1:
            logger.warning(
                f"could not locate a chunk of {source_file.relative_path} in its source text, skipping chunk"
            )
            continue
        cursor = offset

        start_line = _line_number(full_text, offset)
        end_line = _line_number(full_text, offset + len(piece))

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
                text=piece,
                file_path=source_file.relative_path,
                start_line=start_line,
                end_line=end_line,
                language=source_file.language,
                repo=repo,
            )
        )

    return chunks


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
