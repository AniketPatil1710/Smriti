"""BM25 sparse index over code chunks, pickled to disk."""

import pickle
import re
from pathlib import Path

from rank_bm25 import BM25Okapi

import config
from src.ingestion.chunker import Chunk
from src.utils.logger import get_logger

logger = get_logger(__name__)

_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_]+")

# Agent-constructed queries are natural-language questions ("where is X defined?"), not bare
# keywords. Without stopword filtering, common question words dominate a rare identifier's BM25
# score — found via direct testing: an exact, unique symbol name ranked 24th because "where"/
# "is"/"defined" scored higher across docs pages that just repeat those words often. Multi-word
# identifiers (snake_case, etc.) are unaffected — the underscore keeps them one token.
_STOPWORDS = frozenset(
    "a an and are as at be by do does for from has have how in is it of on or that the this to "
    "was were what when where which who why will with would".split()
)


def tokenize(text: str) -> list[str]:
    """Lowercase word/identifier tokenizer, with English stopwords removed — shared between \
    index build and query time."""
    return [t for t in _TOKEN_PATTERN.findall(text.lower()) if t not in _STOPWORDS]


def _index_path() -> Path:
    return config.BM25_DIR / "code_bm25.pkl"


def build_bm25_index(chunks: list[Chunk]) -> None:
    """Build and pickle a BM25 index over `chunks`' text, alongside their chunk_ids in matching order."""
    corpus = [tokenize(c.text) for c in chunks]
    bm25 = BM25Okapi(corpus)

    config.BM25_DIR.mkdir(parents=True, exist_ok=True)
    with _index_path().open("wb") as f:
        pickle.dump({"bm25": bm25, "chunk_ids": [c.chunk_id for c in chunks]}, f)

    logger.info(f"built BM25 index over {len(chunks)} chunks")


def load_bm25_index() -> tuple[BM25Okapi, list[str]]:
    """Load the pickled BM25 index. Raises if ingestion hasn't built one yet."""
    path = _index_path()
    if not path.exists():
        raise RuntimeError("No BM25 index found — run `python ingest.py --repo <url>` first.")
    with path.open("rb") as f:
        data = pickle.load(f)
    return data["bm25"], data["chunk_ids"]


def search_bm25(query: str, top_k: int) -> list[str]:
    """Return the `top_k` chunk_ids ranked by BM25 score, best first."""
    bm25, chunk_ids = load_bm25_index()
    scores = bm25.get_scores(tokenize(query))
    ranked_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
    return [chunk_ids[i] for i in ranked_indices]
