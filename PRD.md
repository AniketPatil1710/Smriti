# PRD — Smriti

**Smriti** (स्मृति — "memory") is a RAG agent that answers questions about a codebase by retrieving from both the **code** and the **git history that shaped it**.

---

## 1. Problem

A developer joining an unfamiliar repository spends days reconstructing context. Existing codebase chatbots index source files and answer *what* the code does. They cannot answer *why* it is the way it is — that knowledge lives in commit messages, PR descriptions, and linked issues, which are never indexed.

Two failure modes in existing tools:

- **Intent questions fail.** "Why is there a retry loop here?" — the answer is in a bug-fix commit from eight months ago, not in the source.
- **Symbol lookup fails.** "Where is `validateUserToken` defined?" — dense embeddings return chunks *about* token validation, not the chunk *containing* the definition.

## 2. Users

**Primary: a developer onboarding onto an unfamiliar repo.** Comfortable with the terminal, impatient, will abandon the tool if the first three answers are vague. Asks a mix of orientation questions ("how is auth structured?"), lookup questions ("where is X defined?"), and intent questions ("why does this exist?").

**Secondary: a maintainer answering the same onboarding questions repeatedly.** Wants to point newcomers at a tool instead of re-explaining.

**Non-users (explicitly out of scope):** teams wanting code generation, refactoring, or PR review. Smriti reads and explains. It does not write code.

## 3. Goals

**Product goal.** A developer can point Smriti at a GitHub repo and get grounded, cited answers to what/where/why questions within one indexing run.

**Engineering goal — the one this project is actually evaluated on.** Demonstrate that multi-index retrieval (code + history) with hybrid dense/BM25 search measurably beats single-index dense retrieval, on an evaluation set derived from real developer intent.

## 4. Features

### P0 — must ship

| # | Feature | Acceptance criteria |
|---|---------|--------------------|
| F1 | Repo ingestion | Clone a public GitHub repo by URL; walk the tree; filter to source files; skip vendored, generated, lock, and binary files. |
| F2 | Code index | Language-aware chunking with `file_path`, `start_line`, `end_line` metadata on every chunk. Persisted to ChromaDB. |
| F3 | History index | Commit messages + PR titles/bodies embedded into a second collection, each carrying `files_touched`. |
| F4 | Hybrid retrieval | Dense (Chroma) + sparse (BM25) rankings fused via Reciprocal Rank Fusion. Single entry point returns ranked chunks. |
| F5 | ReAct agent | Four tools: `read_file`, `list_files`, `semantic_search`, `why_does_this_exist`. Hard iteration cap. |
| F6 | Citations | Every answer cites `file:line` ranges for the chunks it used. No citation → the claim is not made. |
| F7 | Chat interface | Web UI: ask a question, see a streamed answer with clickable citations. |
| F8 | Evaluation harness | Auto-built eval set from merged PRs; recall@k reported across four retrieval configurations. |

### P1 — if time permits

- Repo map: LLM-generated file and directory summaries as a third retrieval layer
- Query routing: classify query type, route to the appropriate index
- Multi-turn conversation memory

### P2 — explicitly deferred, listed as future work

- AST-aware chunking via tree-sitter
- Code graph tools (`find_callers`, `get_dependencies`)
- VS Code extension
- Private repo support
- Incremental re-indexing on new commits

## 5. Success metrics

**Primary:** recall@5 on the auto-generated eval set, measured for four configurations — dense only, BM25 only, hybrid, hybrid + history. Hybrid should beat dense-only. The delta is the headline result.

**Secondary:**
- Intent-question quality: on 20 hand-picked "why" questions, does the answer cite a relevant commit or PR?
- Indexing time and API cost for a mid-size repo (target: under 10 minutes, under $2)
- Answer latency (target: under 15s end to end)

**A negative result is an acceptable outcome** provided the methodology is clean and reported honestly.

## 6. Constraints

- **5-day build window.** Scope is fixed by this. P1 items are cut on any slip.
- Single developer.
- OpenAI API only (`text-embedding-3-small`, `gpt-4o-mini`). Budget under $20 total.
- Public repos only. No authentication, no multi-user state.
- Local-first: everything runs on one machine, persisted to disk.

## 7. Target repository for demo and evaluation

Pick a repo with a substantial merged-PR history — `fastapi`, `flask`, or `requests`. **Verify PR-history depth on day 1**; the eval set depends on it entirely. A small personal repo will not work.

## 8. Out of scope

Code generation. Editing or PR authoring. Real-time file watching. Team or auth features. Any language whose splitter isn't already provided by the chunking library.
