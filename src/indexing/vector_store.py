"""Chroma persistent client and the `code` / `history` collections."""

import chromadb

import config
from src.indexing.embedder import embed_texts
from src.ingestion.chunker import Chunk
from src.ingestion.git_history import HistoryRecord, encode_files_touched
from src.utils.logger import get_logger

logger = get_logger(__name__)

_NO_PR_SENTINEL = -1  # Chroma metadata can't hold None; pr_number=-1 means "no PR"

_client: chromadb.ClientAPI | None = None


def get_client() -> chromadb.ClientAPI:
    global _client
    if _client is None:
        _client = chromadb.PersistentClient(path=str(config.CHROMA_DIR))
    return _client


def _rebuild_collection(
    name: str,
    ids: list[str],
    texts: list[str],
    metadatas: list[dict],
) -> chromadb.Collection:
    """Wipe and repopulate a collection, embedding `texts` and batching `.add()` calls."""
    client = get_client()
    existing_names = {c.name for c in client.list_collections()}
    if name in existing_names:
        client.delete_collection(name)
    collection = client.create_collection(name)

    if not ids:
        logger.warning(f"nothing to index — '{name}' collection created empty")
        return collection

    embeddings = embed_texts(texts)
    for start in range(0, len(ids), config.CHROMA_ADD_BATCH_SIZE):
        end = start + config.CHROMA_ADD_BATCH_SIZE
        collection.add(
            ids=ids[start:end],
            embeddings=embeddings[start:end],
            documents=texts[start:end],
            metadatas=metadatas[start:end],
        )

    logger.info(f"indexed {len(ids)} records into '{name}' collection")
    return collection


def rebuild_code_collection(chunks: list[Chunk]) -> chromadb.Collection:
    """Wipe and repopulate the `code` collection from `chunks`.

    Idempotent per Architecture.md: re-running ingestion rebuilds the collection
    for whichever repo was just walked, rather than accumulating across runs.
    """
    metadatas = [
        {
            "file_path": c.file_path,
            "start_line": c.start_line,
            "end_line": c.end_line,
            "language": c.language,
            "repo": c.repo,
        }
        for c in chunks
    ]
    return _rebuild_collection(
        config.CODE_COLLECTION_NAME, [c.chunk_id for c in chunks], [c.text for c in chunks], metadatas
    )


def rebuild_history_collection(records: list[HistoryRecord]) -> chromadb.Collection:
    """Wipe and repopulate the `history` collection from `records`."""
    metadatas = [
        {
            "type": r.type,
            "sha": r.sha,
            "pr_number": r.pr_number if r.pr_number is not None else _NO_PR_SENTINEL,
            "files_touched": encode_files_touched(r.files_touched),
            "date": r.date,
        }
        for r in records
    ]
    return _rebuild_collection(
        config.HISTORY_COLLECTION_NAME, [r.record_id for r in records], [r.text for r in records], metadatas
    )


def get_code_collection() -> chromadb.Collection:
    return get_client().get_collection(config.CODE_COLLECTION_NAME)


def get_history_collection() -> chromadb.Collection:
    return get_client().get_collection(config.HISTORY_COLLECTION_NAME)
