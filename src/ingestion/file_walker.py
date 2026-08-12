"""Walk a cloned repo, filter to source files: skip vendored, generated, lock, and binary files."""

from dataclasses import dataclass
from pathlib import Path

from config import (
    ALLOWED_EXTENSIONS,
    CANONICAL_DOCS_LANG,
    DOCS_DIR_NAME,
    EXTENSION_LANGUAGE_MAP,
    MAX_FILE_SIZE_BYTES,
    MINIFIED_MARKER,
    SKIP_DIR_NAMES,
    SKIP_FILE_PATTERNS,
)
from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class SourceFile:
    path: Path  # absolute path on disk
    relative_path: str  # path relative to repo root, e.g. "src/auth/tokens.py"
    language: str


def walk_repo(repo_root: Path) -> list[SourceFile]:
    """Walk `repo_root`, returning source files eligible for chunking.

    If a canonical-language docs root exists (`docs/en/`, the common
    mkdocs/Docusaurus i18n convention), only that is indexed — other
    `docs/<lang>/` trees are skipped. Found via a real case: fastapi ships
    13 near-identical doc translations (English is only ~9% of its 1,656
    markdown files), and near-duplicate embeddings across them were
    crowding actual source code out of retrieval results for short queries.
    Repos without this structure (no `docs/en/`) are indexed exactly as
    before — this only activates when the convention is actually present.
    """
    canonical_docs_root = repo_root / DOCS_DIR_NAME / CANONICAL_DOCS_LANG
    only_index_canonical_docs = canonical_docs_root.is_dir()

    files: list[SourceFile] = []
    skipped_size = 0
    skipped_other = 0
    skipped_translation = 0

    for path in repo_root.rglob("*"):
        if not path.is_file():
            continue
        rel_parts = path.relative_to(repo_root).parts
        if any(part in SKIP_DIR_NAMES for part in rel_parts[:-1]):
            continue
        if path.name in SKIP_FILE_PATTERNS or MINIFIED_MARKER in path.name:
            continue
        if path.suffix not in ALLOWED_EXTENSIONS:
            continue
        if (
            only_index_canonical_docs
            and rel_parts[0] == DOCS_DIR_NAME
            and (len(rel_parts) < 2 or rel_parts[1] != CANONICAL_DOCS_LANG)
        ):
            skipped_translation += 1
            continue

        try:
            size = path.stat().st_size
        except OSError as e:
            logger.warning(f"could not stat {path}: {e}")
            skipped_other += 1
            continue
        if size == 0 or size > MAX_FILE_SIZE_BYTES:
            skipped_size += 1
            continue
        if _looks_binary(path):
            skipped_other += 1
            continue

        files.append(
            SourceFile(
                path=path,
                relative_path=str(path.relative_to(repo_root)),
                language=EXTENSION_LANGUAGE_MAP[path.suffix],
            )
        )

    logger.info(
        f"walked {repo_root}: {len(files)} source files, "
        f"{skipped_size} skipped (size), {skipped_translation} skipped (non-canonical docs language), "
        f"{skipped_other} skipped (other)"
    )
    return files


def _looks_binary(path: Path, sample_size: int = 8192) -> bool:
    """Heuristic: a null byte in the first `sample_size` bytes means binary."""
    try:
        with path.open("rb") as f:
            chunk = f.read(sample_size)
    except OSError:
        return True
    return b"\x00" in chunk


def language_breakdown(files: list[SourceFile]) -> dict[str, int]:
    """Count files per language, descending by count."""
    counts: dict[str, int] = {}
    for f in files:
        counts[f.language] = counts.get(f.language, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: kv[1], reverse=True))
