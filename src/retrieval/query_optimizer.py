"""LLM-based query rewriting: turn a possibly-terse query into a fuller,
retrieval-friendlier form, cached by content hash like embeddings.

Evidence this matters, not assumed: the bare term "APIRouter" returned
unusable results from every retrieval mode, while "where is the APIRouter
class defined?" — same intent — correctly surfaced it. That's a phrasing
gap this closes at the retrieval layer, rather than relying on every tool
caller to phrase queries well.
"""

import hashlib
import json
import time

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

from config import CACHE_DIR, LLM_MODEL, QUERY_OPTIMIZER_MAX_RETRIES
from src.utils.logger import get_logger

logger = get_logger(__name__)

_client: OpenAI | None = None

_SYSTEM_PROMPT = (
    "Rewrite the user's search query into a clear, complete question or descriptive phrase "
    "suitable for searching a codebase with embeddings and keyword search. Preserve every "
    "technical term, identifier, and file name exactly as given — never guess or expand what "
    "an identifier means. If the query is already a clear full question, return it unchanged. "
    "Reply with only the rewritten query, nothing else."
)


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI()
    return _client


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _cache_path():
    return CACHE_DIR / f"query_rewrites_{LLM_MODEL}.json"


def _load_cache() -> dict[str, str]:
    path = _cache_path()
    if not path.exists():
        return {}
    with path.open() as f:
        return json.load(f)


def _save_cache(cache: dict[str, str]) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with _cache_path().open("w") as f:
        json.dump(cache, f)


def optimize_query(query: str) -> str:
    """Return a retrieval-friendlier rewrite of `query`.

    Falls back to `query` unchanged if the rewrite call fails — query
    optimization is a quality improvement, never a hard dependency for
    retrieval to function.
    """
    cache = _load_cache()
    key = _hash(query)
    if key in cache:
        return cache[key]

    try:
        rewritten = _rewrite_with_retry(query)
    except RuntimeError as e:
        logger.warning(f"query optimization failed for {query!r}, using original: {e}")
        return query

    cache[key] = rewritten
    _save_cache(cache)
    return rewritten


def _rewrite_with_retry(query: str) -> str:
    client = _get_client()
    last_error: Exception | None = None
    for attempt in range(1, QUERY_OPTIMIZER_MAX_RETRIES + 1):
        try:
            response = client.chat.completions.create(
                model=LLM_MODEL,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": query},
                ],
                temperature=0,
            )
            rewritten = (response.choices[0].message.content or "").strip()
            return rewritten if rewritten else query
        except (AuthenticationError, PermissionDeniedError) as e:
            raise RuntimeError(f"OpenAI authentication failed — check OPENAI_API_KEY in .env: {e}") from e
        except BadRequestError as e:
            raise RuntimeError(f"OpenAI rejected the request (not retrying): {e}") from e
        except (RateLimitError, APIConnectionError, APITimeoutError, APIError) as e:
            last_error = e
            wait = 2**attempt
            logger.warning(
                f"query optimizer call failed ({type(e).__name__}), "
                f"retrying in {wait}s (attempt {attempt}/{QUERY_OPTIMIZER_MAX_RETRIES})"
            )
            time.sleep(wait)

    raise RuntimeError(
        f"query optimizer call failed after {QUERY_OPTIMIZER_MAX_RETRIES} attempts: {last_error}"
    ) from last_error
