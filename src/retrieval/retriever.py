"""Single retrieval entry point: query -> ranked chunks.

Three modes behind one signature: "dense" (Chroma cosine similarity alone),
"bm25" (sparse keyword match alone), "hybrid" (both, fused by RRF). Dense
finds conceptually related code; BM25 finds exact identifiers dense
embeddings can bury — hybrid is what the eval in Phase 7 measures.
"""

from dataclasses import dataclass

import config
from src.indexing.bm25_index import search_bm25
from src.indexing.embedder import embed_texts
from src.indexing.vector_store import get_code_collection, get_history_collection
from src.ingestion.git_history import decode_files_touched
from src.retrieval.hybrid import reciprocal_rank_fusion
from src.retrieval.query_optimizer import optimize_query
from src.retrieval.reranker import rerank_ids
from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: str
    text: str
    file_path: str
    start_line: int
    end_line: int
    language: str
    repo: str


def retrieve(
    query: str,
    top_k: int = config.TOP_K,
    mode: str = config.RETRIEVAL_MODE,
    optimize: bool = False,
    rerank: bool = False,
) -> list[RetrievedChunk]:
    """Return the `top_k` code chunks most relevant to `query`, ranked by `mode`.

    `optimize=True` rewrites `query` into a fuller, retrieval-friendlier form
    before searching (see query_optimizer.py) — evidence this matters: a bare
    term like "APIRouter" retrieves poorly across every mode, while the full
    question "where is the APIRouter class defined?" does not.

    `rerank=True` fetches a wider candidate pool and has an LLM re-score it
    by reading the query and each candidate's actual text together, then
    cuts to `top_k` (see reranker.py) — a comparison dense cosine similarity
    and BM25 term overlap can't make, since neither ever looks at the query
    and a document side by side.
    """
    if optimize:
        query = optimize_query(query)

    fetch_k = config.RERANK_CANDIDATE_POOL if rerank else top_k

    if mode == "dense":
        chunk_ids = _dense_rank(query, fetch_k)
    elif mode == "bm25":
        chunk_ids = search_bm25(query, fetch_k)
    elif mode == "hybrid":
        pool = config.RRF_CANDIDATE_POOL
        fused = reciprocal_rank_fusion([_dense_rank(query, pool), search_bm25(query, pool)])
        chunk_ids = fused[:fetch_k]
    else:
        raise ValueError(f"unknown retrieval mode: {mode!r} (expected 'dense', 'bm25', or 'hybrid')")

    chunks = _fetch_chunks_by_id(chunk_ids)
    if not rerank or not chunks:
        return chunks[:top_k]

    by_id = {c.chunk_id: c for c in chunks}
    reranked_ids = rerank_ids(query, [c.chunk_id for c in chunks], [c.text for c in chunks], top_k)
    return [by_id[i] for i in reranked_ids if i in by_id]


def _dense_rank(query: str, top_k: int) -> list[str]:
    """Chunk IDs ranked by cosine similarity to `query`, best first."""
    query_embedding = embed_texts([query])[0]
    results = get_code_collection().query(query_embeddings=[query_embedding], n_results=top_k)
    return results["ids"][0]


def _fetch_chunks_by_id(chunk_ids: list[str]) -> list[RetrievedChunk]:
    """Fetch chunk text + metadata for `chunk_ids`, preserving the given order.

    Chroma's `.get()` doesn't guarantee it returns rows in the order the ids
    were requested, so results are re-indexed by id before assembling.
    """
    if not chunk_ids:
        return []

    result = get_code_collection().get(ids=chunk_ids)
    by_id = {
        result["ids"][i]: (result["documents"][i], result["metadatas"][i]) for i in range(len(result["ids"]))
    }

    chunks = []
    for chunk_id in chunk_ids:
        if chunk_id not in by_id:
            continue  # stale id (e.g. re-ingested since the sparse index was built)
        text, metadata = by_id[chunk_id]
        chunks.append(
            RetrievedChunk(
                chunk_id=chunk_id,
                text=text,
                file_path=metadata["file_path"],
                start_line=metadata["start_line"],
                end_line=metadata["end_line"],
                language=metadata["language"],
                repo=metadata["repo"],
            )
        )
    return chunks


@dataclass(frozen=True)
class RetrievedHistoryRecord:
    record_id: str
    text: str
    type: str
    sha: str
    pr_number: int | None
    files_touched: list[str]
    date: str


def search_history(query: str, top_k: int = config.TOP_K) -> list[RetrievedHistoryRecord]:
    """Semantic history search: embed `query`, search the history collection generally.

    The other half of Architecture.md §6's "two ways to retrieve history" —
    `get_history_by_file` looks up by a known path, this looks up by meaning
    (e.g. "find past PRs about retry logic" without already knowing the file).
    """
    query_embedding = embed_texts([query])[0]
    collection = get_history_collection()
    results = collection.query(query_embeddings=[query_embedding], n_results=top_k)

    ids = results["ids"][0]
    documents = results["documents"][0]
    metadatas = results["metadatas"][0]

    return [
        RetrievedHistoryRecord(
            record_id=ids[i],
            text=documents[i],
            type=metadatas[i]["type"],
            sha=metadatas[i]["sha"],
            pr_number=None if metadatas[i]["pr_number"] < 0 else metadatas[i]["pr_number"],
            files_touched=decode_files_touched(metadatas[i]["files_touched"]),
            date=metadatas[i]["date"],
        )
        for i in range(len(ids))
    ]


def get_history_by_file(file_path: str, limit: int = config.TOP_K) -> list[RetrievedHistoryRecord]:
    """By-file history lookup: records whose files_touched includes `file_path`, most recent first.

    Chroma metadata filters don't support substring "contains" on a string
    field, so the encoded files_touched field is filtered client-side —
    fine at the scale of one repo's history (thousands of records, not
    millions).
    """
    collection = get_history_collection()
    all_records = collection.get()

    marker = f"{config.FILES_TOUCHED_DELIMITER}{file_path}{config.FILES_TOUCHED_DELIMITER}"
    matches = []
    for i, record_id in enumerate(all_records["ids"]):
        metadata = all_records["metadatas"][i]
        if marker in metadata["files_touched"]:
            matches.append((record_id, metadata, all_records["documents"][i]))

    matches.sort(key=lambda m: m[1]["date"], reverse=True)

    return [
        RetrievedHistoryRecord(
            record_id=record_id,
            text=text,
            type=metadata["type"],
            sha=metadata["sha"],
            pr_number=None if metadata["pr_number"] < 0 else metadata["pr_number"],
            files_touched=decode_files_touched(metadata["files_touched"]),
            date=metadata["date"],
        )
        for record_id, metadata, text in matches[:limit]
    ]
