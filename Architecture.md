# Architecture — Smriti

## 1. Core idea

Two retrieval channels over the same repository, joined by file path.

```
        ┌─────────────────┐         ┌────────────────────┐
        │   CODE INDEX    │         │   HISTORY INDEX    │
        │  source chunks  │◄───────►│  commits + PRs     │
        │  file:line meta │  joined │  files_touched     │
        └────────┬────────┘ on path └─────────┬──────────┘
                 │                            │
         dense + BM25 (RRF)              dense only
                 │                            │
                 └──────────┬─────────────────┘
                            ▼
                     ReAct agent (4 tools)
                            ▼
                  answer + file:line citations
```

The join is the whole point: a question about `auth/tokens.py` retrieves both the code and the commits that changed it.

## 2. Stack

| Layer | Choice | Why |
|---|---|---|
| Language | Python 3.11 | ecosystem |
| API | FastAPI + uvicorn | async, streaming, auto docs |
| Agent | LangChain ReAct | tool-calling loop without writing one |
| LLM | `gpt-4o-mini` | cheap enough to iterate on prompts for days |
| Embeddings | `text-embedding-3-small` | 1536-dim, cheap, fine for code |
| Vector DB | ChromaDB (persistent) | zero-config, local, two collections |
| Sparse | `rank_bm25` | pure Python, pickles to disk |
| Chunking | LangChain `RecursiveCharacterTextSplitter.from_language()` | 9 languages free |
| Git | `GitPython` + GitHub REST API | log locally, PR bodies remotely |
| Eval | custom + `PyGithub` | no framework needed |
| Frontend | Vanilla HTML/CSS/JS | no build step, no npm, saves half a day |

**Deliberately not used:** React (build step costs more than it returns here), Pinecone/Weaviate (network dependency), LlamaIndex (overlaps LangChain; one framework is enough), tree-sitter (deferred to P2).

## 3. Folder structure

```
smriti/
├── README.md
├── requirements.txt
├── .env.example                 # OPENAI_API_KEY, GITHUB_TOKEN
├── .gitignore                   # data/, .env, __pycache__
├── config.py                    # paths, model names, chunk sizes, top_k
│
├── app.py                       # FastAPI entry — serves UI + /chat
├── ingest.py                    # CLI: python ingest.py --repo <url>
├── evaluate.py                  # CLI: python evaluate.py --config hybrid
│
├── src/
│   ├── ingestion/
│   │   ├── cloner.py            # clone into data/repos/<name>
│   │   ├── file_walker.py       # walk, filter extensions, skip vendor/lock/binary
│   │   ├── chunker.py           # language-aware split → Chunk objects w/ line numbers
│   │   └── git_history.py       # git log + GitHub API → HistoryRecord objects
│   │
│   ├── indexing/
│   │   ├── embedder.py          # batched embedding calls, retry, on-disk cache
│   │   ├── vector_store.py      # two Chroma collections: code, history
│   │   └── bm25_index.py        # rank_bm25 over code chunks, pickled
│   │
│   ├── retrieval/
│   │   ├── hybrid.py            # RRF fusion of dense + sparse rankings
│   │   └── retriever.py         # single entry point: query → ranked chunks
│   │
│   ├── agent/
│   │   ├── agent.py             # ReAct loop, tool registry, max_iterations guard
│   │   ├── prompts.py           # system prompt + tool descriptions
│   │   └── tools/
│   │       ├── read_file.py
│   │       ├── list_files.py
│   │       ├── semantic_search.py
│   │       └── why_does_this_exist.py
│   │
│   └── utils/
│       ├── logger.py
│       └── citations.py         # chunk metadata → file:line links
│
├── eval/
│   ├── build_eval_set.py        # mine merged PRs → queries + ground truth
│   ├── metrics.py               # recall@k, MRR
│   ├── data/eval_set.json
│   └── results/                 # ablation output — committed to git
│
├── frontend/
│   ├── index.html
│   └── static/{style.css, app.js}
│
├── data/                        # gitignored
│   ├── repos/  chroma/  bm25/  cache/
│
└── tests/
    ├── test_chunker.py          # line numbers survive chunking
    └── test_hybrid.py           # RRF ordering is correct
```

## 4. Data contracts

Fix these on day 1. Everything downstream depends on them.

**Chunk** — one unit of code, one embedding:
```python
{
  "chunk_id":   "src/auth/tokens.py:42-78",   # path + line range, unique
  "text":       "def validate_token(...):\n    ...",
  "file_path":  "src/auth/tokens.py",
  "start_line": 42,
  "end_line":   78,
  "language":   "python",
  "repo":       "fastapi",
}
```

**HistoryRecord** — one commit or PR:
```python
{
  "record_id":     "commit:a3f9c21",
  "text":          "<commit message + PR body, concatenated>",
  "type":          "commit" | "pr",
  "sha":           "a3f9c21",
  "pr_number":     4821,                    # None for plain commits
  "files_touched": ["src/auth/tokens.py", "tests/test_auth.py"],
  "date":          "2024-03-11",
}
```
`files_touched` is the join key. Chroma metadata cannot hold lists — store it as a delimited string (`"|src/auth/tokens.py|tests/test_auth.py|"`) and substring-match on it.

**EvalItem**:
```python
{
  "query":              "add retry logic when the token refresh endpoint times out",
  "ground_truth_files": ["src/auth/tokens.py"],
  "pr_number":          4821,
  "source":             "merged_pr",
}
```

## 5. Flows

### Indexing — `ingest.py --repo <url>`

```
clone repo
  ├─ walk tree → filter files → chunk → embed → chroma["code"]
  │                                  └─────────→ bm25 index → pickle
  └─ git log --numstat ──┐
     GitHub PR API ──────┴→ HistoryRecords → embed → chroma["history"]
```

Runs once per repo, 5–10 minutes for a mid-size repo. Idempotent: re-running wipes and rebuilds the collections for that repo.

### Query — `POST /chat`

```
question
  └→ ReAct agent
       ├─ semantic_search(q)        → retriever → dense ∪ BM25 → RRF → top-k chunks
       ├─ why_does_this_exist(path) → history collection, filtered by files_touched
       ├─ read_file(path, start, end)
       └─ list_files(dir)
     ↓ (max 6 iterations)
   answer + citations[] → streamed to UI
```

### Evaluation — `evaluate.py --config <name>`

Bypasses the agent entirely — retrieval only, which is what's being measured and is deterministic and fast.

```
eval_set.json
  └→ for each query: retrieve top-5 → compare file paths to ground_truth_files
     → recall@5, MRR → eval/results/<config>.json
```

Four configs: `dense`, `bm25`, `hybrid`, `hybrid_history`. The comparison table across these four is the project's headline output.

## 6. Retrieval detail

**RRF fusion.** For each document `d` appearing in ranking lists:

```
score(d) = Σ  1 / (k + rank_i(d)),    k = 60
```

Rank-based, so dense cosine scores and BM25 scores never need to be normalized against each other. Take the top 5 after fusion.

**History retrieval** works two ways: semantically (embed the question, search the history collection) and by-file (filter `files_touched` for a given path, return most recent N). The `why_does_this_exist` tool uses the by-file path; general history questions use the semantic one.

## 7. Known risks

| Risk | Mitigation |
|---|---|
| Line numbers lost in chunking | Track offsets manually during split; unit test it on day 1 |
| Agent context blowup from `list_files` | Cap tool output at 2000 chars; return directory summaries, not full listings |
| Agent loops between tools | `max_iterations=6`, hard fail with partial answer |
| GitHub API rate limits | Authenticated token (5000/hr); cache PR responses to disk |
| Embedding cost on large repos | Cache by content hash; cap repo size at ~5000 files |
| Chroma metadata can't store lists | Delimited-string encoding for `files_touched` |
