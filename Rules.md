# Rules — Smriti

Constraints for any AI assistant writing code in this repository. Read this before touching any file.

---

## Scope discipline

1. **Build only what the current phase in `Phases.md` calls for.** Do not implement P1 or P2 features early, and do not "improve" completed phases while working on a later one.
2. **No speculative abstraction.** No plugin systems, no strategy patterns, no base classes with one subclass. This is a 5-day project — write the direct version.
3. **If a requirement is ambiguous, stop and ask.** Do not invent product behaviour and do not silently pick an interpretation.
4. **Never edit `data/`.** It's generated and gitignored.

## Stack — fixed

**Use:** `fastapi`, `uvicorn`, `langchain`, `langchain-openai`, `langchain-community`, `chromadb`, `rank_bm25`, `GitPython`, `PyGithub`, `python-dotenv`, `pydantic`, `pytest`, `tiktoken`.

**Do not add any other dependency without asking.** In particular, do not introduce:

- React, Next.js, Vue, or any npm build step — the frontend is vanilla HTML/CSS/JS
- LlamaIndex, Haystack, or a second agent framework — LangChain only
- Pinecone, Weaviate, Qdrant, FAISS — ChromaDB only
- tree-sitter — deferred to P2, do not add it "while you're in there"
- SQLAlchemy or any ORM — there is no relational database
- Celery, Redis, or a task queue — ingestion is a blocking CLI script
- Tailwind or any CSS framework — plain CSS with the tokens in `Design.md`

**Models are fixed:** `gpt-4o-mini` for the agent, `text-embedding-3-small` for embeddings. Both referenced from `config.py`, never hardcoded at a call site.

## Configuration

5. **Every tunable lives in `config.py`.** Chunk size, overlap, `top_k`, RRF constant, `max_iterations`, model names, paths. No magic numbers in logic files.
6. **Secrets come from environment variables via `python-dotenv`.** Never hardcode a key, never commit `.env`, and keep `.env.example` current when a new variable is added.

## Error handling

7. **Fail loudly at ingestion, degrade gracefully at query time.** A malformed repo URL should raise immediately with a clear message. A single unreadable file during a 3000-file walk should log a warning and be skipped, not abort the run.
8. **Never swallow an exception.** No bare `except:`, no `except Exception: pass`. Catch the specific error, log it with context, then re-raise or return a typed failure.
9. **External calls get retries.** OpenAI and GitHub calls use exponential backoff with a cap of 3 attempts. Rate-limit responses (429) wait and retry; auth errors (401/403) fail immediately with an actionable message.
10. **Tools return errors as strings to the agent, never as exceptions.** `read_file` on a missing path returns `"Error: file not found: <path>"` so the agent can recover. An exception kills the loop.

## Agent safety

11. **`max_iterations = 6`, enforced.** On exhaustion, return the partial answer plus a note that the agent hit its limit — never loop indefinitely.
12. **Every tool output is truncated to `MAX_TOOL_OUTPUT_CHARS` (2000).** `list_files` on a large repo returns directory-level counts, not thousands of paths. This is the most common failure mode in this class of project; treat the cap as non-negotiable.
13. **The agent reads. It never writes.** No file creation, modification, deletion, or shell execution outside the ingestion script's own git clone.
14. **No claim without a citation.** If the agent states something about the codebase, the supporting chunk's `file_path` and line range must appear in the citations array. If retrieval returned nothing relevant, say so — do not answer from the model's general knowledge of the library.

## Code conventions

15. Type hints on every function signature. Pydantic models for anything crossing a boundary (API request/response, tool input/output).
16. Docstrings on public functions: one line on what, one on why if non-obvious.
17. Use the `logger` from `src/utils/logger.py`. No `print()` outside CLI entry points.
18. Files stay under ~300 lines. If one grows past that, it's doing two jobs — split it.
19. `pathlib.Path` for all paths, never string concatenation.
20. Follow the data contracts in `Architecture.md` exactly. Field names, types, and the `files_touched` delimited-string encoding are fixed — changing one means updating every consumer in the same commit.

## Testing

21. Two tests are mandatory and written alongside the code, not after: line numbers survive chunking (`test_chunker.py`) and RRF produces the correct ordering (`test_hybrid.py`).
22. **Never write a test that asserts on live LLM output.** Mock the model. Tests must run without network access or an API key.

## Cost

23. Cache embeddings by content hash in `data/cache/`. Re-indexing an unchanged file must not re-embed it.
24. Batch embedding calls (100 chunks per request). Never embed in a one-per-request loop.
25. Before any operation that would exceed ~$1 in API spend, print an estimate and require confirmation.

## Things to say out loud rather than work around

26. If a phase's acceptance criteria can't be met with the fixed stack, say so and propose options — do not quietly add a dependency.
27. If you notice a design flaw in these documents, flag it. These docs are not sacred; silently deviating from them is the problem, not disagreeing with them.
28. Do not claim something works if you haven't run it. "This should work" is fine; "this works" requires having executed it.
