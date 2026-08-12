# Phases — Smriti

Nine phases across five days. Each has an exit criterion — a thing you can run that either works or doesn't. **Do not start a phase until the previous one's exit criterion passes.**

---

## Day 0 (evening before) — Phase 0: Verify assumptions

The whole plan rests on two things. Check them before writing any code.

- [ ] Target repo picked (`fastapi`, `flask`, or `requests`) and cloned locally
- [ ] `GITHUB_TOKEN` works; you can list merged PRs via the API
- [ ] At least **100 merged PRs** have a description over 50 characters and touch 1–3 files — this is your eval set, and if it isn't there the project's headline result is impossible
- [ ] `OPENAI_API_KEY` works; a test embedding call returns

**Exit:** a printed count of usable PRs, ≥100. If it's below that, pick a different repo *now*.

**If this fails on all candidate repos:** fall back to a hand-written eval set of 30 questions. Slower, weaker, but the project still ships.

---

## Day 1 — Base RAG working end to end

Goal: something ugly that answers a question. Do not polish anything today.

### Phase 1 — Skeleton + ingestion (3h)

Repo structure per `Architecture.md`. `config.py` with every constant. `.env` loading. Logger.

`cloner.py` clones by URL. `file_walker.py` walks and filters — extension allowlist, skip `node_modules`, `venv`, `dist`, `.git`, lockfiles, minified files, anything over 500KB.

**Exit:** `python ingest.py --repo <url>` prints a file count and a per-language breakdown.

### Phase 2 — Chunking with line numbers (2h)

`chunker.py` using `RecursiveCharacterTextSplitter.from_language()`. Track line offsets manually while splitting.

Write `test_chunker.py` **now**, not later: reconstruct a chunk's line range from the original file and assert the text matches. Getting this wrong on day 1 silently breaks citations on day 3.

**Exit:** `pytest tests/test_chunker.py` passes; chunks carry correct `start_line`/`end_line`.

### Phase 3 — Code index (2h)

`embedder.py` with batching (100/request), retry, content-hash cache. `vector_store.py` creating the `code` collection.

**Exit:** ingestion populates Chroma; a manual query returns plausible chunks with intact metadata.

### Phase 4 — Agent + minimal UI (4h)

ReAct agent with three tools: `read_file`, `list_files`, `semantic_search`. `max_iterations=6`, tool output capped at 2000 chars — build both caps in now, not after the first runaway loop.

FastAPI `/chat`. A single HTML page with a text box and a response area. Unstyled.

**Exit:** ask "where is authentication handled?" in the browser and get a grounded answer.

> **End of Day 1: you have a working standard RAG codebase chatbot.** Everything from here makes it better and proves it. If you stopped now, you'd have the reference project.

---

## Day 2 — The differentiators

### Phase 5 — History index (4h)

`git_history.py`: `git log --numstat` for commits, GitHub API for PR titles and bodies, joined on merge commit SHA. Build `HistoryRecord` objects. Remember `files_touched` is a delimited string, not a list — Chroma metadata can't hold lists.

Embed into the `history` collection. Add the `why_does_this_exist(file_path)` tool: filter history by `files_touched`, return the most relevant records.

**Exit:** ask "why does `<some file>` exist?" and get an answer citing an actual commit or PR.

### Phase 6 — Hybrid retrieval (3h)

`bm25_index.py` over the same chunks, pickled to disk. `hybrid.py` implementing RRF (`k=60`). `retriever.py` as the single entry point, with a config flag selecting `dense` / `bm25` / `hybrid`.

Write `test_hybrid.py` alongside it.

**Exit:** "where is `<exact function name>` defined?" returns the defining chunk in the top 3 — the query dense retrieval alone fails.

> **End of Day 2: the system is architecturally complete.** Days 3–4 measure it and package it.

---

## Day 3 — Evaluation. The day that decides the project.

### Phase 7 — Eval set + ablations (5h)

`build_eval_set.py`: merged PRs → `{query: PR description, ground_truth_files: files changed}`. Filter to 1–3 files and descriptions over 50 chars. Manually spot-check 20 items and delete the nonsense ones — auto-generated data always has some.

`metrics.py`: recall@5, MRR. `evaluate.py` runs retrieval only, no agent.

Run all four configs: `dense`, `bm25`, `hybrid`, `hybrid_history`. Write results to `eval/results/` and commit them.

**Exit:** a four-row comparison table with real numbers.

**If hybrid doesn't beat dense:** report it honestly. Check for leakage first (are eval PRs inside your indexed history?), then publish whatever's true. A clean negative result beats an unverified claim.

### Phase 8 — Citations (3h)

`citations.py`: chunk metadata → structured citation objects. Agent returns `answer` plus `citations[]`. UI renders them as `file:line` links that expand the chunk.

**Exit:** every answer in the UI shows which files and lines it drew from.

---

## Day 4 — Ship

### Phase 9 — Polish and package (6h)

Design pass per `Design.md` — timebox to 2 hours. Restyle, don't rebuild.

README: the problem, the two-index architecture diagram, **the results table**, setup instructions, cost and timing, honest limitations, future work (tree-sitter chunking, code graph tools, query routing).

Record a 60-second demo GIF showing three questions: a lookup, a conceptual, and a "why". Repo description filled in. `.env.example` current. Fresh-clone test: does setup actually work from scratch?

**Exit:** a stranger can clone, install, ingest, and query without asking you anything.

---

## Day 5 — Buffer

Deliberately unallocated. Something in phases 5–7 will overrun; this is where it goes.

If nothing overran, spend it on **one** P1 item — repo map summaries are the highest value — or on expanding the eval set. Do not start two.

---

## Cut order

When you slip, cut in this order without deliberating:

1. Design polish → plain CSS, ship it
2. P1 features → all of them
3. Multi-turn conversation → single-turn only
4. Eval set size → 50 items instead of 100
5. History index semantic search → keep `why_does_this_exist` by-file only

**Never cut:** citations, the eval table, or the README. Those are the project's entire value on a resume.

---

## Progress tracking

Once Phase 1 starts, maintain `Memory.md` at the repo root — what's done, what's in progress, decisions made and why, known bugs. Update it at the end of every phase. It's what keeps an AI assistant oriented across sessions without re-reading the codebase.
