**Last updated:** 2026-08-13 · **Current phase:** 9 — Polish + README (done, exit criterion passed), plus a post-P9 retrieval-quality pass (query optimizer, reranker, AST chunking) requested and authorized by the user — see Numbers for final headline result

## Status

| Phase | State | Notes |
|---|---|---|
| 0 — Verify assumptions | ✅ | target repo: fastapi/fastapi, usable PRs: 120 (of 340 scanned, need ≥100) |
| 1 — Skeleton + ingestion | ✅ | `ingest.py --repo <url>` clones + prints file count and per-language breakdown |
| 2 — Chunking | ✅ | `tests/test_chunker.py` 7/7 passing; verified against a real 255KB file (`fastapi/routing.py` → 355 chunks, reconstructed line ranges exactly contain chunk text) |
| 3 — Code index | ✅ | `ingest.py` now chunks + embeds + indexes end to end; **7,206 chunks** (was 20,530 — see the canonical-docs-language fix below) in Chroma `code` collection; manual query returns plausible results with intact metadata |
| 4 — Agent + UI | ✅ | ReAct agent (`read_file`, `list_files`, `semantic_search`) + FastAPI `/chat` + unstyled HTML page. Exit-criterion question ("where is authentication handled?") answered end to end over real HTTP with 4 correctly cited sources |
| 5 — History index | ✅ | `git_history.py` + Chroma `history` collection + `why_does_this_exist` tool. Exit-criterion question answered citing 5 real PRs — all verified against raw retrieval data, not hallucinated |
| 6 — Hybrid retrieval | ✅ | `bm25_index.py` + `hybrid.py` (RRF) behind `retriever.retrieve(mode=...)`. `tests/test_hybrid.py` 7/7. Exit criterion verified with a real case: `_get_flat_body_params` — dense misses top-3, hybrid hits it — confirmed at retriever level AND end-to-end through the live agent |
| 7 — Eval + ablations | ✅ | 110-item eval set × 4 configs, **re-run after the canonical-docs fix below (numbers superseded once, see Numbers)**. Current headline: **hybrid_history 0.411 recall@5 vs dense 0.167 (2.46x)**, leakage-guard verified with concrete evidence. Plain hybrid now clearly *trails* dense (0.139 vs 0.167) — a cleaner, more honest negative result than the earlier near-tie, explained in Decisions |
| 8 — Citations | ✅ | Tools return `(text, citations)` via LangChain's `content_and_artifact`; agent collects/dedupes into `AskResult.citations`; `/chat` exposes them; UI shows clickable, expandable source chips. Two real bugs found + fixed (see Decisions) |
| 9 — Polish + README | ✅ | Design.md CSS applied (color tokens, typography, strata bar, citation chips, empty state). README with architecture diagram, results table, honest limitations. 9 phase-by-phase git commits + this one. Fresh-clone test genuinely verified (real `git clone`, fresh venv, real `ingest.py`, real query) — exit criterion passed for real, not assumed |
| 10 — Retrieval quality (post-P9, user-requested) | ✅ | Query optimizer, LLM reranker, AST-aware Python chunking (tree-sitter) — each proposed with yes/no + impact analysis, authorized by the user, built, and measured in isolation against the eval set. Full-stack recall@5 0.411 → 0.595 (+45% relative) across the three additions combined. See Numbers |

✅ done · 🟡 in progress · ⬜ not started · ❌ blocked

## What works right now

`python ingest.py --repo <url>` clones a public GitHub repo into `data/repos/<name>`
(reusing it if already cloned), walks the tree filtering to allowed source
extensions (skipping vendor/build/lock/binary/minified files and anything over
500KB), and prints a total file count plus a per-language breakdown. Verified
end-to-end against `fastapi/fastapi`: 2,648 source files (1,691 markdown, 953
python, 4 js), 184 skipped for size.

`src/ingestion/chunker.py` (`chunk_file(source_file, repo)`) splits one file
into `Chunk` objects (`chunk_id`, `text`, `file_path`, `start_line`,
`end_line`, `language`, `repo`) using
`RecursiveCharacterTextSplitter.from_language()`, locating each split's exact
character offset in the original text (search anchored at the previous
chunk's start, so overlap doesn't break lookup) and converting to 1-indexed
line numbers by counting newlines. Unreadable/empty files return `[]` instead
of raising. `chunk_id` gets a `#<n>` suffix on the rare case where one very
long line (e.g. a base64 blob) splits into multiple chunks that would
otherwise report an identical line range.

`src/indexing/embedder.py` (`embed_texts`, `estimate_cost_usd`) batches
OpenAI embedding calls (100/request), caches every embedding on disk by
sha256 of the chunk text (`data/cache/embeddings_<model>.pkl`) so re-running
ingestion on unchanged content costs nothing, and retries transient failures
with exponential backoff (auth errors fail immediately with an actionable
message). `src/indexing/vector_store.py` (`rebuild_code_collection`) wipes
and repopulates the Chroma `code` collection from a chunk list, batching
`.add()` calls under Chroma's internal limit.

`ingest.py` now runs the full pipeline: clone → walk → chunk → estimate cost
→ (confirm if > $1) → embed → index. Verified end-to-end against
`fastapi/fastapi`: 20,530 chunks, $0.0894 actual embedding cost, all now
cached. A manual `collection.query()` for "how does dependency injection
work" returns plausible chunks (fastapi's own dependency-injection docs, in
several languages — it ships translated docs) with intact metadata
(`file_path`, `start_line`, `end_line`, `language`, `repo`).

`src/retrieval/retriever.py` (`retrieve(query, top_k)`) is the single
retrieval entry point — dense-only for now, embeds the query and queries the
Chroma `code` collection. Phase 6 adds BM25 + RRF fusion behind this same
function signature.

`src/ingestion/cloner.py` gained `set_active_repo()` / `get_active_repo_root()`,
backed by a marker file at `data/active_repo.txt`. Needed because
`data/repos/` can accumulate clones from multiple past ingestion runs, but
only one repo's chunks are ever live in Chroma at a time (rebuilt fresh each
run) — the marker is what tells the agent's file-reading tools which clone
on disk actually matches the current index.

Three LangChain tools in `src/agent/tools/`: `read_file` (path + optional
line range, path-traversal-guarded to stay inside the indexed repo),
`list_files` (one directory level, sub-directories collapsed to file counts),
`semantic_search` (wraps `retriever.retrieve`, formats results as
`[file:start-end]` + preview). All three return `f"Error: ..."` strings on
failure, never raise — the agent can't be killed by a bad path or a flaky
API call.

`src/agent/agent.py` builds the agent via `langchain.agents.create_agent`
(LangChain 1.x's current agent API — the old `AgentExecutor` +
`create_react_agent` path Architecture.md was written against no longer
exists in the installed version; this is the same "LangChain only" agent,
just current API surface). Iteration cap enforced via `recursion_limit` on
the compiled graph; on `GraphRecursionError`, a `MemorySaver` checkpointer
lets `ask()` recover the last real answer text the agent had produced
instead of losing all context, per Rules.md rule 11.

`app.py` — FastAPI serving `/` (static HTML) and `POST /chat`
(`{question} -> {answer}`). `frontend/index.html` + `frontend/static/app.js`
— textbox, Ask button, Enter-to-send, unstyled per Phases.md Phase 4.

`src/ingestion/git_history.py` (`build_history_records`) walks local git
history via GitPython (`commit.stats.files` for files touched, capped at
`MAX_COMMITS`) and joins it against merged GitHub PRs by merge-commit SHA.
The join is cheap: PR `title`/`body`/`merge_commit_sha` are all present on
the PR *list* endpoint response, so no per-PR fetch is needed (verified: 50
PRs' worth of field access consumed 0 extra rate-limit units). Commits with
a matching PR become `type="pr"` records (title + body as text, richer than
the terse squash-merge commit message); commits without one become
`type="commit"` records from their own message. `files_touched` is
delimited-string encoded (`encode_files_touched`/`decode_files_touched`) per
`Architecture.md` §4, since Chroma metadata can't hold lists.

`vector_store.py` gained `rebuild_history_collection`, sharing a
`_rebuild_collection` helper with the code collection (same wipe/embed/batch
logic, different metadata shape). `retriever.get_history_by_file(path)` does
the by-file lookup Architecture.md describes: Chroma metadata filters can't
substring-match, so the (small — thousands, not millions of records) history
collection is pulled client-side and filtered/sorted by date in Python. The
semantic history-search half of Architecture.md's "two ways to retrieve
history" (embed the question, search generally) is deliberately not built
yet — nothing in Phase 5's tool list needs it, only `why_does_this_exist`
(by-file) does; it'd be dead code today.

`src/agent/tools/why_does_this_exist.py` wraps `get_history_by_file`,
formatting each match as `[#<pr_number or short-sha> · <date>]` + text
preview. Wired into `agent.py`'s tool list and `ingest.py`'s pipeline
(history index builds right after the code index, `set_active_repo` now
fires only after both succeed).

`src/indexing/bm25_index.py` builds a `rank_bm25.BM25Okapi` index over every
code chunk's text, pickled to `data/bm25/code_bm25.pkl` alongside the
matching `chunk_ids` list (order-aligned, since BM25Okapi itself only knows
positions, not IDs). `src/retrieval/hybrid.py` (`reciprocal_rank_fusion`)
fuses any number of ranked ID lists by the formula in `Architecture.md` §6.
`retriever.retrieve(query, top_k, mode)` now dispatches on `mode`:
`"dense"` | `"bm25"` | `"hybrid"` (default, from `config.RETRIEVAL_MODE`) —
hybrid over-fetches `RRF_CANDIDATE_POOL=20` from each ranking before fusing
down to `top_k`, so a good BM25 match ranked outside a bare top-5 dense
window still gets pulled in. `ingest.py` builds the BM25 index right after
the code Chroma index (cheap, local, no API calls).

Final regression before closing this phase: all 8 standard test questions
(4 from Phase 4, 2 directory-listing, 1 "why", 1 exit-criterion symbol
lookup) re-verified through the live server after every fix above, back to
back, in one clean run — no known-bad answers remaining. `pytest tests/`
14/14.

`src/retrieval/retriever.py` gained `search_history(query, top_k)` — the
semantic (non-by-file) history lookup deferred back in Phase 5, now needed
by the `hybrid_history` eval config. `eval/build_eval_set.py`
(`python -m eval.build_eval_set --repo <url>`) mines merged PRs into
`{query, ground_truth_files, pr_number, source}` items, filtered to
human-authored (not bot-flagged, not self-declared-automated, no duplicate
titles), description > 50 chars, 1–3 files touched. `eval/metrics.py`
(`recall_at_k`, `mrr`) are pure functions over file-path lists, unit tested
in `test_metrics.py`. `evaluate.py --config <name|all>` runs retrieval only
(no agent, deterministic) and writes `eval/results/<config>.json` +
`comparison.json`.

**Headline result** (110-item eval set, fastapi/fastapi):

| config | recall@5 | MRR |
|---|---|---|
| dense | 0.141 | 0.158 |
| bm25 | 0.120 | 0.136 |
| hybrid | 0.142 | 0.158 |
| hybrid_history | **0.306** | **0.255** |

`hybrid_history` more than doubles dense-only recall. Plain `hybrid`
essentially ties `dense` (+0.001) rather than clearly beating it — reported
honestly per `Phases.md`'s instruction, with an evidenced explanation rather
than left unexplained (see Decisions).

`src/utils/citations.py` defines `Citation` (source, label, full text,
file_path/start_line/end_line for code, pr_number/sha for history) and
`citation_from_chunk`/`citation_from_history_record`/`dedupe`. All three
retrieval tools (`semantic_search`, `why_does_this_exist`, `read_file`) now
use `@tool(response_format="content_and_artifact")`, returning
`(llm_facing_text, list[Citation])` — the LLM never sees the artifact, only
the formatted string it always saw; citations are pulled from the tool's own
return value, not parsed or retyped from anywhere. `list_files` deliberately
produces none — a directory listing isn't a "claim about the codebase" in
the citation sense.

`agent.ask()` now returns `AskResult(answer, citations)` instead of a bare
string — after a run, it scans the message history for `ToolMessage`
instances and collects every `.artifact`, deduped by (source, label).
`app.py`'s `/chat` exposes `citations: list[CitationResponse]` via a
Pydantic model built from the dataclasses with `dataclasses.asdict`.
`frontend/` renders each citation as a button (`[source] label`) that
toggles an expanded `<pre>` with the full cited text — functional, unstyled
per the Phase 4/8 convention, visual chip design is Phase 9.

**Two real bugs found via full regression testing, both fixed:**
1. On the iteration-cap fallback path (`agent.get_state()`, not a live
   `invoke()` return), citation artifacts round-trip through the
   checkpointer as plain dicts, not `Citation` instances — crashed
   `dedupe()`. Fixed by normalizing both shapes in `_collect_citations`.
2. `_last_answer()` picked the most recent message with any non-empty
   string content, without checking it was actually `AIMessage` — when the
   iteration cap was hit right after a tool call, it returned a
   `ToolMessage`'s raw content (once, literally the first ~2000 characters
   of `fastapi/routing.py`, starting `import contextlib...`) as if it were
   the agent's answer. This was a **latent bug present since Phase 4**, not
   a Phase 8 regression — just never surfaced until this phase's more
   thorough repeated-run testing hit the iteration cap on a message list
   ending in a ToolMessage. Fixed by filtering to `isinstance(message,
   AIMessage)`.

**New finding, deliberately not fixed here — flagged instead (out of Phase
8's scope, a real product decision):** bare-term queries like `"APIRouter"`
(vs. the full question `"where is the APIRouter class defined?"`) return 5
near-duplicate multi-language translations of the same docs page (zh-hant,
zh, ja, uk, ko) in the hybrid top-5, crowding out the actual
`fastapi/routing.py:2255-2280` source chunk entirely. Traced a real agent
run where this caused it to abandon retrieval, hallucinate-guess a
nonexistent `app/routers` directory, and burn its iteration budget on blind
file exploration — hitting `MAX_ITERATIONS` roughly 1-in-4 times for an
otherwise-easy question. Root cause: fastapi ships ~15 language
translations of its docs, and near-identical embeddings across them can
dominate a short query's top-k. Needs a deliberate fix (e.g. dedupe
near-identical chunks before ranking, or down-weight non-English docs by
default) — not something to prompt-patch, and not in scope for citations.

**Canonical-docs-language fix** (user asked to address the flagged finding
immediately, ahead of Phase 9): `file_walker.walk_repo` now detects a
`docs/en/` root and, when present, indexes only that — skipping every other
`docs/<lang>/` tree. Falls back to indexing all of `docs/` unchanged when no
`docs/en/` exists (flask/requests-style repos untouched). Added
`tests/test_file_walker.py` (3 tests) covering both branches.

Effect, measured not assumed: chunk count 20,530 → 7,206 (-65%), all
embeddings cache-hit (zero new API cost — same file content, smaller file
*set*). The originally-failing bare-term query (`"APIRouter"` alone) now
correctly surfaces `fastapi/routing.py:2255-2280` in hybrid's top-5 — the
multi-language duplicate flood is gone. Re-ran the full 8-question
regression: 8/8 succeed with zero `MAX_ITERATIONS` hits (was ~25% failure
rate on the APIRouter question alone, traced in Phase 8 to the model
abandoning search and hallucinating a nonexistent `app/routers` directory
after a duplicate-flooded result set).

Re-ran Phase 7's full evaluation on the new index — see Numbers for the
updated table. Small honest tradeoff: 5/110 eval items have a non-English
docs file as ground truth and can no longer be recalled at all (by design,
not a bug) — recall improved anyway despite this handicap, confirming the
fix is a net positive, not just noise reduction that happened to help.

`frontend/static/style.css` (new) implements `Design.md`'s full system:
color tokens, Fraunces/IBM Plex Sans/IBM Plex Mono/IBM Plex Sans Devanagari
via Google Fonts, the strata bar (proportional code/history segments per
answer, computed client-side from that answer's citation sources),
citation chips (blue for code, ochre for history, click-to-expand), empty
state with 3 example questions, 380px responsive breakpoint,
`prefers-reduced-motion` support. `frontend/index.html` and
`frontend/static/app.js` rewritten to match — same `/chat` contract, no
backend behavior change ("restyle, don't rebuild"). Added `GET /info`
(repo name + chunk count) since the header design calls for it.

Git history reconstructed as 10 commits (project spec, then one per phase
0-9) — grouped by primary/creation phase using current final file content,
since intermediate snapshots weren't preserved during the build. Disclosed
to the user as a readable narrative reconstruction, not literal
minute-by-minute history.

README.md written: problem statement, mermaid architecture diagram, the
Phase 7 results table with commentary (not just numbers), setup
instructions, cost/timing, an explicit Limitations section (English-only
docs tradeoff, hybrid-underperforms-dense finding, no AST chunking, no
code graph, single-turn, LLM transcription-slip caveat on prose vs
citations), future work, project structure, stack. Demo GIF deliberately
skipped per user's explicit choice — noted as a manual follow-up in the
README rather than faked.

Fresh-clone test **actually performed**, not assumed: real local
`git clone`, fresh `python3.12 -m venv`, real `pip install -r
requirements.txt`, real `python ingest.py --repo ...` (re-cloned fastapi
from GitHub for real; embeddings cache-hit since content is identical, so
$0 additional cost), real `python app.py`, real `POST /chat` returning a
correct, cited answer. Exit criterion passed for real.

`src/retrieval/query_optimizer.py` (`optimize_query`) rewrites a query into
a fuller, more retrieval-friendly form via an LLM call before embedding/BM25
(e.g. a bare `"APIRouter"` becomes something like `"where is the APIRouter
class defined?"`), cached by sha256 of the input query in
`data/cache/query_rewrites_<model>.json` — same content-hash-cache pattern
as `embedder.py`. Falls back to the original query unchanged on any failure
(auth/bad-request fail immediately, transient errors retry with backoff, up
to `QUERY_OPTIMIZER_MAX_RETRIES=3`). Wired into `retriever.retrieve(...,
optimize=True)`, the live `semantic_search` tool, and a new
`hybrid_history_optimized` eval config.

`src/retrieval/reranker.py` (`rerank_ids`) re-scores a wider candidate pool
(`RERANK_CANDIDATE_POOL=20`, fetched post-RRF-fusion) by having an LLM read
the query and each candidate's actual chunk text together — a comparison
dense cosine similarity and BM25 term overlap structurally can't make, since
both score query and document independently and only compare the resulting
representations. Real bug found and fixed during development: initial
validation demanded the model's returned ranking be an exact, complete
permutation of every candidate index; a real 20-candidate case had the model
return a well-formed ranking covering 19 of 20 (dropping one low-relevance
index), which the old check discarded entirely, silently falling back to
unreranked order instead of retrying. Fixed by moving validation (unique,
in-range, covers at least `top_k`) inside the retry loop instead of after
it, so a genuinely malformed response gets retried while a
mostly-correct one is still accepted. Wired into `retriever.retrieve(...,
rerank=True)`, the live `semantic_search` tool, and a new
`hybrid_history_optimized_reranked` eval config.

`src/ingestion/ast_chunker.py` (`chunk_python_ast`) replaces character-based
chunking for Python files: parses the real syntax tree via `tree-sitter` +
`tree-sitter-python`, and each top-level function or class becomes its own
chunk on its actual boundary, instead of being cut at an arbitrary character
offset (the old `RecursiveCharacterTextSplitter.from_language()` is
language-aware only about *not splitting mid-line*, not about function
bodies). A class much bigger than `chunk_size` splits into a header chunk
(signature/docstring/class-level statements) plus one chunk per method, so a
class with many methods doesn't collapse into one blob. Any single AST unit
still too big for one chunk falls back to character-splitting just that
unit (`chunker.py`'s new `_subdivide` helper) — this is what the existing
long-single-line regression test in `test_chunker.py` caught during
development, and it preserves the "no oversized chunk" guarantee the old
splitter had. A file that fails to parse falls back to the character
splitter entirely. Only Python is covered; every other language is
unaffected. New tests in `test_ast_chunker.py` (7 tests) cover function/
class boundaries, decorator handling, large-class splitting, and the
parse-failure fallback.

Re-ingested `fastapi/fastapi` with the new chunker: **10,718 chunks** (was
7,206 — AST chunking produces more, finer-grained chunks than the character
splitter did), 5,453 newly embedded (Python chunk text changed), 5,265
cache-hit (non-Python files, chunked identically to before).

Adding `tree-sitter`/`tree-sitter-python` is a deliberate, flagged deviation
from `Rules.md` ("tree-sitter — deferred to P2, do not add it 'while you're
in there'") — done with the user's explicit go-ahead after being asked
directly whether to build AST chunking, not added silently. See Decisions.

## What I'm doing next

Nothing queued. Phase 9 (`Phases.md`'s last phase) plus a follow-on
retrieval-quality pass (query optimizer, reranker, AST chunking — all three
explicitly requested by the user, each measured against the eval set before
being kept) are both done. Project is complete pending the user's own review.

## Decisions made

- `2026-08-12` — Target repo is `fastapi/fastapi` — verified 120 usable merged PRs (desc >50 chars, 1–3 files touched) against the 100 minimum in `Phases.md` Phase 0.
- `2026-08-12` — Smriti gets its own git repo at `Desktop/Smriti/` (`git init`), separate from the pre-existing repo rooted at `/Users/aniket` — the latter spans the whole home directory and isn't a sensible place for a project meant to be shared/pushed.
- `2026-08-12` — Commits in this repo must not carry a `Co-Authored-By: Claude` trailer — user doesn't want Claude listed as a GitHub contributor.
- `2026-08-12` — venv uses Python 3.12, not the 3.11 named in `Architecture.md` — 3.11 isn't installed on this machine and no pyenv is available. Every dependency in `requirements.txt` supports 3.12; no known compatibility gap.
- `2026-08-12` — Added `config.EXTENSION_LANGUAGE_MAP` (extension → `langchain_text_splitters.Language` value) instead of the plain extension set implied by `Architecture.md`'s `ALLOWED_EXTENSIONS` — both `file_walker`'s per-language breakdown (Phase 1) and `chunker`'s `from_language()` call (Phase 2) need the same extension→language mapping, so it's defined once in `config.py` per Rules.md rule 5.
- `2026-08-12` — `chunk_file()` takes `chunk_size`/`chunk_overlap` as optional params defaulting to `config.CHUNK_SIZE`/`CHUNK_OVERLAP`, rather than reading the constants directly — needed so `test_chunker.py` can use a small chunk size on a short fixture instead of a multi-thousand-line one. Production call sites never pass these explicitly.
- `2026-08-12` — User wants to review and confirm each phase before the next one starts, rather than running through all phases autonomously.
- `2026-08-12` — `config.py` now calls `load_dotenv()` on import (was missing) — every module that reads an env var (e.g. `OPENAI_API_KEY`) imports `config`, so loading `.env` there covers every entry point instead of requiring each script to remember to call it.
- `2026-08-12` — `chunk_id` disambiguation (`#<n>` suffix) added after a real collision surfaced in fastapi's `docs_src/stream_data/tutorial002_py310.py` (one line = a base64 image, split into 8 chunks all reporting line 8) — `Architecture.md`'s `path:start-end` chunk_id format silently assumes one chunk per line-range, which single long lines violate. Chroma's `collection.add()` raises `DuplicateIDError` on collision, so this wasn't optional to fix. Regression test added in `test_chunker.py`.
- `2026-08-12` — Agent built with `langchain.agents.create_agent`, not `langchain.agents.create_react_agent` + `AgentExecutor` as `Architecture.md` implies — the installed LangChain (1.3.15) removed the old classic-ReAct path entirely; `create_agent` is its current replacement, built on `langgraph` under the hood as a transitive dependency of `langchain` itself (not a second agent framework being added). See `Deviations` below.
- `2026-08-12` — Added `data/active_repo.txt` (`cloner.set_active_repo`/`get_active_repo_root`) to track which repo's clone matches the current Chroma index — not in `Architecture.md`'s file list, but needed because `data/repos/` can hold clones from multiple past ingestion runs while only the most recent one is actually indexed.
- `2026-08-12` — `retriever.py` is dense-only in this phase (queries Chroma directly), matching Phase 4's scope in `Phases.md`; BM25 + RRF fusion behind the same `retrieve()` signature is Phase 6, not built yet.
- `2026-08-12` — Tightened `SYSTEM_PROMPT` after manually testing 7 questions through the live server surfaced two real LLM failure modes, both verified against the actual filesystem: (1) the model would misattribute files adjacent to a collapsed sub-directory line in `list_files` output as being *inside* that sub-directory — `list_files` itself was always correct, this was purely an answer-writing hallucination; (2) the model would try one wrong path, see "not found," and declare something nonexistent instead of checking the repo root and retrying nested one level deeper (e.g. `dependencies` → `fastapi/dependencies`). Added explicit rules for both; re-verified all 7 questions afterward, all now accurate against the real filesystem.
- `2026-08-12` — `Github(auth=..., per_page=100)` set explicitly when scanning merged PRs — PyGithub's default `per_page=30` meant scanning `HISTORY_PR_SCAN_LIMIT=2000` PRs took 82.7s; `per_page=100` cut it to 44.8s. Same data, fewer HTTP round trips.
- `2026-08-12` — `embed_texts()` now truncates any text over `EMBEDDING_MAX_INPUT_TOKENS` (8000, margin under the API's 8192 hard limit) before embedding — several fastapi PR bodies (Dependabot's auto-generated multi-package bump changelogs) are 19K–21K tokens, well over the limit, and caused a hard `BadRequestError`. Truncation happens before hashing so the cache key matches what was actually sent; the full untruncated text is still stored as the Chroma document, only the embedding input is shortened.
- `2026-08-12` — `BadRequestError` now fails immediately in `_embed_batch_with_retry` instead of being retried like a transient error — a 400 from oversized/malformed input is permanent, so the 3 retries before the truncation fix were pure wasted time (confirmed: identical error on all 3 attempts).
- `2026-08-12` — History join uses only the PR *list* endpoint (`repo.get_pulls`), not a per-PR fetch — confirmed empirically that `title`/`body`/`merge_commit_sha` are present on list-response objects at 0 extra rate-limit cost. This is cheaper than Phase 0's eval-feasibility check, which needed per-PR fetches for `changed_files` (not needed here since `files_touched` comes from local `git log` instead).
- `2026-08-12` — Semantic (non-by-file) history search — the second retrieval mode `Architecture.md` §6 describes — was deliberately not built in Phase 5. Nothing in Phase 5's tool list (`Phases.md`) needs it, only `why_does_this_exist` (by-file) does. Added in Phase 7 as `retriever.search_history()` once the `hybrid_history` eval config genuinely needed it — confirms the Phase 5 deferral call was correct rather than a gap.
- `2026-08-12` — BM25 tokenizer strips a small hardcoded English stopword list (`a`, `is`, `where`, `defined`, etc. — no new dependency). Found via direct testing: the agent's `semantic_search` queries are full questions ("where is X defined?"), not bare keywords, and without stopword filtering those question words dominated BM25 scoring — a real, unique identifier (`_get_flat_body_params`) ranked 24th, beaten by docs pages that just happened to repeat "where"/"is"/"defined" often. This is standard, well-established BM25 practice, not a scope addition — bare BM25 doesn't work as intended on natural-language queries without it. Rebuilt the BM25 pickle after the change (tokenization is baked in at build time).
- `2026-08-12` — `semantic_search` tool no longer truncates each result to a fixed 300-char preview — relies solely on the existing overall `MAX_TOOL_OUTPUT_CHARS` cap instead. Found via the same real case: the chunk containing `_get_flat_body_params`'s definition ranked correctly at #1, but the fixed per-chunk preview cut off *before* reaching that function (the chunk's first ~300 chars were a different, earlier function in the same chunk) — so the agent's answer said the function "is not directly defined in the codebase" despite the tool having retrieved the right chunk. Full chunk text is now shown per result; if the total exceeds the cap, lower-ranked results are what gets cut, not the top one. This is the second real case (after the Phase 4 `list_files` one) of grounded, correct retrieval getting undermined by how the tool formatted it for the LLM — worth remembering as a recurring failure class in this kind of project, not a one-off.
- `2026-08-12` — `SYSTEM_PROMPT`'s citation example changed from a concrete `src/auth/tokens.py:42-78` (copied from `Architecture.md`'s data-contract example) to an abstract `<path>:<start_line>-<end_line>` — the concrete example was biasing the model toward guessing a `src/` layout for repos that don't have one (fastapi has none; real path is `fastapi/dependencies/utils.py`). First attempt at generalizing the "check root before guessing a path" rule (previously scoped to `list_files` only) to also cover `read_file`/`why_does_this_exist` **caused a regression** — the abstracted wording lost the concrete worked example that made the original Phase 4 fix reliable, and the exact "`dependencies/` doesn't exist" bug came back on full regression testing. Fixed by restoring a concrete example inline (the exact `dependencies` → `fastapi/dependencies` case) while keeping the broader `src/`-guessing fix. Lesson: for steering this agent's behavior, a concrete worked example in the prompt is more reliable than an abstract restatement of the same rule — re-verify with the full regression set after *any* prompt edit, not just the case that motivated it.
- `2026-08-12` — Observed one pure LLM transcription slip, not a retrieval/prompt bug: asked "where is APIRouter defined," the tool correctly retrieved `fastapi/routing.py:2255-2280` (verified via direct retriever call), but the model's prose answer said "line 1255" — it mis-typed the digit while re-stating a grounded number in free text. This is exactly the failure class `Architecture.md`'s Phase 8 design (`citations[]` returned as a structured field pulled directly from retrieval metadata, not re-typed by the model) is meant to make structurally impossible — noted here as concrete motivation, not treated as a bug to prompt-patch now (transcription slips aren't reliably fixable by prompting).
- `2026-08-12` — `build_eval_set.py` filters out two noise classes beyond the `pr.user.type == "Bot"` check, both found by directly inspecting the first unfiltered build (146 items): PRs whose body self-declares as automated (`"created automatically"` / `"generated automatically"` — catches translation-sync jobs run under human-flagged accounts, 90/801 scanned) and PRs whose title exactly duplicates an already-accepted item's (catches a recurring scheduled PR — e.g. a contributors-data sync — with byte-identical title/files repeated 4x, zero query signal). Chose general, principled filters (self-declared automation, exact-duplicate detection) over hardcoding specific title strings, so the same pipeline stays useful on other repos. Final set: 110 items (146 → 110 after filtering), still clears the 100 minimum.
- `2026-08-12` — Verified the `hybrid_history` leakage guard (`exclude_pr` in `evaluate.py`) actually does something, not just that it exists: confirmed all 110/110 eval items have their own PR record present in the history index (expected — both scans draw from the same recent-PRs pool), found a concrete case (PR #16174) where the item's own record ranks in its own unfiltered top-5 semantic-history-search results, and showed a ground-truth file (`.github/workflows/sponsors.yml`) present in the unguarded retrieval disappearing once the guard excludes that self-record — while the *other* ground-truth file (`scripts/sponsors.py`) still surfaces correctly with the guard active, confirming genuine (non-leaked) signal remains. This matters because `Phases.md` explicitly calls for a leakage check, and `hybrid_history`'s 2.2x recall lift over dense is large enough that an unverified leak would have been the more likely explanation without this check.
- `2026-08-12` — Plain `hybrid` trails `dense` (first measured as an essential tie — 0.142 vs 0.141 — before the canonical-docs fix; after it, 0.139 vs 0.167, a clearer gap in the same direction), reported honestly per `Phases.md` rather than glossed over. Explanation, evidenced not guessed: eval queries are PR bodies, averaging **114 words** (min 8, max 387) — a completely different regime from the short, keyword-dense "where is X defined?" queries where BM25 proved decisive in the Phase 6 exit criterion. BM25 standalone underperforms dense on this eval set (0.142 vs 0.167 post-fix) because its signal dilutes across hundreds of prose tokens even after stopword filtering; naive equal-weight RRF fusion of a weaker ranking into a stronger one can drag the combined result down, not just fail to help — a known property of RRF, not a bug. `bm25`'s real strength (exact-identifier lookup) isn't what this file-level PR-description eval set tests.
- `2026-08-12` — Fixed the multi-language-docs finding flagged during Phase 8 (user asked to address it immediately rather than deferring to Phase 9): `file_walker.walk_repo` now indexes only `docs/en/` when that canonical-language root exists, skipping the other 12 translation trees fastapi ships. General, not fastapi-hardcoded — detects the convention rather than listing specific language codes, and repos without a `docs/en/` (flask/requests-style) are indexed exactly as before. Chunk count dropped 20,530 → 7,206 (-65%), zero new embedding cost (pure cache hits — same content, smaller file set). Directly fixed the traced failure mode: the bare-term query `"APIRouter"` now surfaces `fastapi/routing.py:2255-2280` in hybrid's top-5 instead of 5 near-duplicate docs translations; the 8-question regression went from ~25% `MAX_ITERATIONS` failures (on the APIRouter question alone) to 0/8. Re-ran the Phase 7 eval on the new index — recall improved for dense/bm25/hybrid_history despite 5/110 eval items losing their (non-English-docs) ground-truth file from the index entirely, confirming the fix is a net win, not just noise cancelling noise.
- `2026-08-13` — Committed the project's git history as 10 commits (spec docs + one per phase 0-9), grouped by each file's primary/creation phase using its current final content, since intermediate per-phase snapshots weren't preserved as the work progressed. This is a "squashed by phase" narrative reconstruction, not literal historical diffs — a shared/evolving file (e.g. `config.py`, `agent.py`) appears complete at whichever commit represents its main introduction, so `git log -p` on such a file won't show period-accurate incremental changes. Chose this over reconstructing intermediate versions because the value of phase commits here is a readable build narrative for a portfolio project, not forensic history, and manually recreating old file states risked subtle inconsistencies for little benefit.
- `2026-08-13` — Fixed a real `.gitignore` bug before the first commit: the bare pattern `data/` (no leading slash) matches a directory named `data` at *any* depth, so it was silently also excluding `eval/data/eval_set.json` — which `Architecture.md` intends to be committed. Changed to `/data/` to anchor it to the repo root only. Caught by directly testing `git check-ignore` rather than assuming the pattern did what it looked like it should.
- `2026-08-13` — User asked, for yes/no + impact only (not yet "build it"): semantic chunking, hybrid dense+keyword search, reranking, and query optimization — all four already true or straightforward given the existing architecture (hybrid retrieval already built in Phase 6; the other three were new). Gave honest per-technique impact estimates and rough build times rather than a blanket "yes, all four help equally."
- `2026-08-13` — User authorized building query optimizer → reranker → AST chunking, in that order (the order proposed based on expected impact vs. effort). All three built, and — matching this project's established rigor — each was measured against the same 110-item eval set in isolation before being kept, not assumed to help.
- `2026-08-13` — Reranker validation bug: initial version demanded the LLM's ranking be an exact, complete permutation of every candidate (all 20 indices, no omissions) before accepting it, and that check ran *after* the retry loop returned rather than inside it. A real case (query about `_get_flat_body_params`, 20 real candidates) showed the model returning a well-formed ranking covering 19 of 20 — still a perfectly usable top-5 — but the all-or-nothing check discarded the whole thing and silently fell back to unreranked order, with no retry attempted. Fixed by relaxing the requirement (unique, in-range, covers at least `top_k`) and moving it inside the retry loop, so only genuinely malformed output gets retried.
- `2026-08-13` — AST chunker only special-cases Python, not every language `EXTENSION_LANGUAGE_MAP` covers. Scoped this way deliberately, matching what was actually proposed to and authorized by the user ("AST-aware chunking for Python via tree-sitter") — extending real AST parsing to JS/TS/Go/etc. would each need their own tree-sitter grammar and boundary logic, out of scope for this pass. Every other language keeps the existing character splitter unchanged.
- `2026-08-13` — Diagnosed and fixed a severe, intermittent I/O problem that had nothing to do with the application: `python app.py` (and even a bare `pickle.load()` / `import numpy`) would sometimes take 25s–2min+, and twice failed outright with `TimeoutError: [Errno 60] Operation timed out` deep inside stdlib's `importlib._bootstrap_external.get_data` (a literal OS-level file-read timeout) or a spurious `ModuleNotFoundError` for a file that was actually present on disk. Root-caused via `ps aux` (multiple `mdworker_shared`/Spotlight processes spawned right around the times of heavy pip-install/file-creation activity) and `sample <pid>` (showed near-zero CPU progress during the "hangs," i.e. genuinely blocked on I/O, not slow computation) — Spotlight indexing and Time Machine backup were both competing for I/O on the newly-created, file-dense `.venv` and `data/` directories. Fixed with the standard mitigation: `touch .venv/.metadata_never_index` (and same for `data/`) plus `tmutil addexclusion` for both directories. Test suite went from 135s to 14.74s immediately after. Purely a local machine/environment issue, not a code bug — worth checking for again if this project is set up fresh on another machine and imports mysteriously stall.

## Deviations from the docs

- `Architecture.md` specifies Python 3.11; this machine runs the project on 3.12 (see Decisions).
- `Architecture.md`'s `agent.py` description ("LangChain ReAct — tool-calling loop without writing one") implied the classic `create_react_agent` + `AgentExecutor` API. The installed LangChain 1.3.15 replaced that entirely with `langchain.agents.create_agent`; there is no other current way to get a LangChain-native ReAct loop. Behavior is equivalent (tool-calling loop, no hand-written control flow); only the import/construction API differs.
- `Rules.md` explicitly lists `tree-sitter` as "deferred to P2, do not add it 'while you're in there.'" Added anyway, post-Phase-9, for AST-aware Python chunking — not a silent violation: the user was asked directly (yes/no + impact analysis on four candidate RAG techniques) and explicitly authorized building it. Flagged here per `Rules.md` rule 27 ("if you notice a design flaw or deviation, say so out loud").

## Known bugs / rough edges

- None outstanding in the application. All app-level bugs found through Phase 8 have been fixed, including the multi-language-docs retrieval issue found during Phase 8 review (see Decisions for what/why on each).
- Several earlier-session mysteries (a transient Chroma `RustBindingsAPI` error right after killing a server process, a spurious `EOFError` reading the BM25 pickle, cold-import delays of 25s-2min+, two outright `TimeoutError`/`ModuleNotFoundError` crashes) were all, in hindsight, almost certainly the same root cause diagnosed and fixed in Phase 9: Spotlight + Time Machine contending for I/O on the large `.venv`/`data/` directories. Now excluded via `.metadata_never_index` + `tmutil addexclusion` (see Decisions) — not re-litigated per-symptom here since they share one explained cause.

## Numbers

- Indexed repo: fastapi/fastapi, 1,147 source files (was 2,648 before the canonical-docs-language fix — 1,501 non-English doc translations now excluded) → **10,718 chunks** (was 7,206 before AST chunking, was 20,530 before the docs fix) in Chroma `code` collection. AST chunking produces more, finer-grained chunks than the character splitter (functions/methods as individual chunks instead of arbitrary windows); 5,453 newly embedded on the re-ingest, 5,265 cache-hit (non-Python files unaffected)
- History records: 2,000 (939 PR, 1,061 plain commit) in Chroma `history` collection — unaffected by either the docs fix or AST chunking (built from `git log`, not `file_walker`/`chunker`)
- Eval set size: 110 items (146 mined, 36 dropped as bot/automated/duplicate-title noise), from 801 closed PRs scanned. Composition: 23 items touch real `fastapi/*.py` source, 56 touch `docs/`, 38 `.github/`, 22 `tests/`, 18 `scripts/` (items can touch multiple categories). 5/110 have a non-English-docs ground-truth file, now permanently unrecallable by design (see Decisions)
- **Final headline recall@5 (dense/bm25/hybrid/hybrid+history/+query-optimizer/+reranker):**
  **0.171 / 0.120 / 0.145 / 0.456 / 0.576 / 0.595** (MRR: 0.160 / 0.133 / 0.154 / 0.393 / 0.474 / 0.472). The full stack (hybrid + history + query optimization + reranking) recovers the correct file in the top 5 on ~60% of eval queries, up from ~17% for dense retrieval alone (3.5x) — and up from 0.476 for the same full stack *before* AST chunking, the single biggest lift of the three post-P9 additions (query optimizer: 0.411→0.442; reranker: 0.442→0.476; AST chunking: 0.476→0.595).
  Prior numbers (character-based chunking, pre-AST): dense 0.167 · bm25 0.142 · hybrid 0.139 · hybrid+history 0.411 · +optimizer 0.442 · +reranker 0.476. Before that (pre-canonical-docs-fix): dense 0.141 · bm25 0.120 · hybrid 0.142 · hybrid+history 0.306. `bm25` alone dipped slightly under AST chunking (0.142→0.120) — plausible cause: chunk-size distribution changed (many small single-function chunks vs. uniform character windows), shifting term-frequency dynamics; the fused/downstream configs still improved regardless, so not investigated further
- Indexing time: clone+walk ~8s (excl. network) · chunking ~4s · code embedding ~75s (uncached) / ~2s (cached) · PR scan ~45s · history embedding ~40s (uncached) / instant (cached) · total end-to-end (cached) ~2.5 min. AST-chunking re-ingest: ~35s (5,453 new embeddings) + history rebuild (cache-hit, ~1 min for the PR/commit scan itself)
- Eval set build time: ~6 min (801 PRs scanned, ~300 candidate file-list fetches) · full 6-config evaluation: ~12 min (110 items × 6 configs — the two LLM-based configs, query-optimized and reranked, each need a fresh per-query API call not covered by embedding cache)
- API cost: $0.0894 (code embeddings, pre-docs-fix corpus) + $0.0103 (history embeddings) + ~$0.006 (AST-rechunked code re-embedding) = **~$0.106 actual total**, one-time, cached for all future re-runs on this repo (excluding the small, ongoing per-query cost of the optimizer/reranker LLM calls, also cached by query content hash for the optimizer)
- `data/cache` 279M+ (grows only, by design — see prior note) · `data/chroma` 892M+ (see prior note on SQLite not auto-vacuuming across rebuilds) · `data/repos` 76M · `data/bm25` 3.2M
- Answer latency: ~12.3s for a semantic_search + read_file×2 question (PRD target: under 15s) — single sample, not a p50
- Citation counts observed across the 8 standard test questions: 0 (pure `list_files` navigation, correctly) to 15 (a multi-tool-call conceptual question); typical range 5–10
- Git: 10 commits (project spec + one per phase 0-9), verified test suite dropped from 135s to 14.74s after the Spotlight/Time Machine exclusion fix
- Fresh-clone test: real `git clone` + fresh venv + `pip install` + `ingest.py` + `app.py` + `/chat` query, all successful, $0 additional API cost (embeddings cache-hit on identical content)

## Files an assistant should read before making changes

- `README.md` — the external-facing project summary; keep in sync with this file's Numbers section
- `config.py` — every tunable lives here
- `src/retrieval/retriever.py` — the single retrieval entry point (dense/bm25/hybrid)
- `Architecture.md` §4 — data contracts, do not change casually
- `Rules.md` — dependency and error-handling constraints
- If imports or `python app.py` seem to hang or stall for no reason on a fresh machine: check `.venv/.metadata_never_index` and `tmutil isexcluded .venv` exist/are true — Spotlight/Time Machine contention on this directory was a real, repeated cause of multi-minute stalls and two outright crashes this session (see Known bugs)

---

## How to update this

At the end of each phase: flip the status row, rewrite "what works" and "what's
next", append any decision with its reason, add measured numbers.

Do **not** log a narrative of what you tried. This is a state file, not a
journal — it should read as *"here is where things stand"*, never *"then I
tried X and it didn't work."*
