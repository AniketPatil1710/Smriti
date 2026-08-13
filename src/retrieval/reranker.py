"""LLM-based reranking: after the fast dense/BM25/RRF pass narrows a large
corpus down to a small candidate pool, re-score that pool by having the
model see the query and each candidate's actual text together — something
dense cosine similarity and BM25 term overlap can't do, since both compare
independently-computed representations rather than the query and the
document directly.
"""

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

from config import LLM_MODEL, RERANK_MAX_RETRIES
from src.utils.logger import get_logger

logger = get_logger(__name__)

_client: OpenAI | None = None
_PREVIEW_CHARS = 400

_SYSTEM_PROMPT = (
    "You are ranking code search results by relevance to a query. You will be given a query and a "
    'numbered list of candidate code chunks. Return a JSON object {"ranking": [...]} listing the '
    "candidate numbers in order from most to least relevant to the query. Include every candidate "
    "number exactly once."
)


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI()
    return _client


def rerank_ids(query: str, candidate_ids: list[str], previews: list[str], top_k: int) -> list[str]:
    """Re-score `candidate_ids` (paired with `previews`, same order) for relevance to `query`.

    Returns the `top_k` best ids, most relevant first. Falls back to the
    input order truncated to top_k on any failure — a reranker should only
    ever improve or preserve an existing ranking, never block retrieval.
    """
    if not candidate_ids:
        return []

    try:
        order = _rank_with_retry(query, previews, top_k)
    except RuntimeError as e:
        logger.warning(f"reranking failed for {query!r}, keeping original order: {e}")
        return candidate_ids[:top_k]

    return [candidate_ids[i] for i in order[:top_k]]


def _rank_with_retry(query: str, previews: list[str], top_k: int) -> list[int]:
    """Return a validated ranking (unique, in-range indices, covering at least top_k of them).

    Deliberately doesn't require every candidate to be ranked — found via a
    real case with 20 candidates: the model returned a well-formed ranking
    covering 19 of them, dropping one. That's still a perfectly usable
    top-5, so rejecting the whole ranking over one missing low-relevance
    index would throw away a mostly-correct result for no reason. What does
    get retried: duplicates, out-of-range indices, or too few to fill top_k.
    """
    n = len(previews)
    numbered = "\n\n".join(f"[{i}] {p[:_PREVIEW_CHARS]}" for i, p in enumerate(previews))
    user_content = f"Query: {query}\n\nCandidates:\n{numbered}"

    client = _get_client()
    last_error: Exception | None = None
    for attempt in range(1, RERANK_MAX_RETRIES + 1):
        try:
            response = client.chat.completions.create(
                model=LLM_MODEL,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                temperature=0,
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content or "{}"
            parsed = json.loads(content)
            ranking = parsed.get("ranking")
            if not isinstance(ranking, list):
                raise ValueError(f"response had no valid 'ranking' list: {content!r}")
            order = [int(i) for i in ranking]

            if len(set(order)) != len(order):
                raise ValueError(f"ranking has duplicate indices: {order}")
            if any(i < 0 or i >= n for i in order):
                raise ValueError(f"ranking has out-of-range indices for {n} candidates: {order}")
            if len(order) < min(top_k, n):
                raise ValueError(f"ranking only covers {len(order)}/{n} candidates, need >= {min(top_k, n)}")

            return order
        except (AuthenticationError, PermissionDeniedError) as e:
            raise RuntimeError(f"OpenAI authentication failed — check OPENAI_API_KEY in .env: {e}") from e
        except BadRequestError as e:
            raise RuntimeError(f"OpenAI rejected the request (not retrying): {e}") from e
        except (RateLimitError, APIConnectionError, APITimeoutError, APIError) as e:
            last_error = e
            wait = 2**attempt
            logger.warning(
                f"reranker call failed ({type(e).__name__}), retrying in {wait}s (attempt {attempt}/{RERANK_MAX_RETRIES})"
            )
            time.sleep(wait)
        except (json.JSONDecodeError, ValueError, TypeError) as e:
            last_error = e
            logger.warning(f"reranker returned an invalid ranking (attempt {attempt}/{RERANK_MAX_RETRIES}): {e}")

    raise RuntimeError(f"reranker call failed after {RERANK_MAX_RETRIES} attempts: {last_error}") from last_error
