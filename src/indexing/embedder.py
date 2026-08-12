"""Batched embedding calls with content-hash caching and retry."""

import hashlib
import pickle
import time
from pathlib import Path

import tiktoken
from openai import (
    APIConnectionError,
    APIError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    OpenAI,
    PermissionDeniedError,
    RateLimitError,
)

from config import (
    CACHE_DIR,
    EMBEDDING_BATCH_SIZE,
    EMBEDDING_COST_PER_1M_TOKENS,
    EMBEDDING_MAX_INPUT_TOKENS,
    EMBEDDING_MAX_RETRIES,
    EMBEDDING_MODEL,
)
from src.utils.logger import get_logger

logger = get_logger(__name__)

_client: OpenAI | None = None
_encoding: tiktoken.Encoding | None = None
_TOKEN_ENCODING = "cl100k_base"  # encoding used by text-embedding-3-small


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI()  # reads OPENAI_API_KEY from the environment
    return _client


def _get_encoding() -> tiktoken.Encoding:
    global _encoding
    if _encoding is None:
        _encoding = tiktoken.get_encoding(_TOKEN_ENCODING)
    return _encoding


def _truncate_to_token_limit(text: str) -> str:
    """Truncate `text` to the API's max input tokens. Code chunks never hit this (bounded by \
    CHUNK_SIZE); history records (PR bodies especially) can be arbitrarily long."""
    encoding = _get_encoding()
    tokens = encoding.encode(text)
    if len(tokens) <= EMBEDDING_MAX_INPUT_TOKENS:
        return text
    logger.warning(
        f"truncating a text from {len(tokens)} to {EMBEDDING_MAX_INPUT_TOKENS} tokens "
        f"before embedding (starts: {text[:80]!r})"
    )
    return encoding.decode(tokens[:EMBEDDING_MAX_INPUT_TOKENS])


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _cache_path() -> Path:
    return CACHE_DIR / f"embeddings_{EMBEDDING_MODEL}.pkl"


def _load_cache() -> dict[str, list[float]]:
    path = _cache_path()
    if not path.exists():
        return {}
    with path.open("rb") as f:
        return pickle.load(f)


def _save_cache(cache: dict[str, list[float]]) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with _cache_path().open("wb") as f:
        pickle.dump(cache, f)


def uncached_texts(texts: list[str]) -> list[str]:
    """Return the subset of `texts` (post-truncation) not already present in the embedding cache."""
    cache = _load_cache()
    return [t for t in (_truncate_to_token_limit(t) for t in texts) if _hash(t) not in cache]


def estimate_cost_usd(texts: list[str]) -> float:
    """Estimate the API cost in USD to embed the uncached subset of `texts`."""
    missing = uncached_texts(texts)
    if not missing:
        return 0.0
    encoding = _get_encoding()
    n_tokens = sum(len(encoding.encode(t)) for t in missing)
    return (n_tokens / 1_000_000) * EMBEDDING_COST_PER_1M_TOKENS


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed `texts`, batching API calls and skipping anything already cached by content hash.

    Returns embeddings in the same order as `texts`. Texts longer than the
    API's token limit are truncated before embedding (and before hashing, so
    the cache key matches what was actually sent) — this only affects what's
    embedded, not the original text stored as the Chroma document.
    """
    if not texts:
        return []

    texts = [_truncate_to_token_limit(t) for t in texts]
    cache = _load_cache()
    hashes = [_hash(t) for t in texts]
    missing = [i for i, h in enumerate(hashes) if h not in cache]

    if missing:
        client = _get_client()
        for start in range(0, len(missing), EMBEDDING_BATCH_SIZE):
            batch_indices = missing[start : start + EMBEDDING_BATCH_SIZE]
            batch_texts = [texts[i] for i in batch_indices]
            batch_embeddings = _embed_batch_with_retry(client, batch_texts)
            for i, embedding in zip(batch_indices, batch_embeddings):
                cache[hashes[i]] = embedding
        _save_cache(cache)
        logger.info(f"embedded {len(missing)} new chunks, {len(texts) - len(missing)} served from cache")
    else:
        logger.info(f"all {len(texts)} chunks served from cache")

    return [cache[h] for h in hashes]


def _embed_batch_with_retry(client: OpenAI, texts: list[str]) -> list[list[float]]:
    last_error: Exception | None = None
    for attempt in range(1, EMBEDDING_MAX_RETRIES + 1):
        try:
            response = client.embeddings.create(model=EMBEDDING_MODEL, input=texts)
            return [d.embedding for d in response.data]
        except (AuthenticationError, PermissionDeniedError) as e:
            raise RuntimeError(f"OpenAI authentication failed — check OPENAI_API_KEY in .env: {e}") from e
        except BadRequestError as e:
            # a 400 from malformed/oversized input is permanent — retrying it changes nothing
            raise RuntimeError(f"OpenAI rejected the request as invalid (not retrying): {e}") from e
        except (RateLimitError, APIConnectionError, APITimeoutError, APIError) as e:
            last_error = e
            wait = 2**attempt
            logger.warning(
                f"OpenAI embedding call failed ({type(e).__name__}), "
                f"retrying in {wait}s (attempt {attempt}/{EMBEDDING_MAX_RETRIES})"
            )
            time.sleep(wait)

    raise RuntimeError(
        f"OpenAI embedding call failed after {EMBEDDING_MAX_RETRIES} attempts: {last_error}"
    ) from last_error
