"""Central configuration. Every tunable lives here — no magic numbers in logic files."""

from pathlib import Path

from dotenv import load_dotenv

# --- Paths ---
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")
DATA_DIR = BASE_DIR / "data"
REPOS_DIR = DATA_DIR / "repos"
CHROMA_DIR = DATA_DIR / "chroma"
BM25_DIR = DATA_DIR / "bm25"
CACHE_DIR = DATA_DIR / "cache"
EVAL_DIR = BASE_DIR / "eval"
EVAL_SET_PATH = EVAL_DIR / "data" / "eval_set.json"
EVAL_RESULTS_DIR = EVAL_DIR / "results"
ACTIVE_REPO_MARKER = DATA_DIR / "active_repo.txt"  # name of the repo currently indexed in Chroma

# --- Models ---
LLM_MODEL = "gpt-4o-mini"
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIM = 1536

# --- Ingestion ---
MAX_FILE_SIZE_BYTES = 500_000  # skip files over 500KB

# extension -> langchain_text_splitters.Language value; shared by file_walker
# (per-language breakdown) and chunker (from_language splitting).
EXTENSION_LANGUAGE_MAP = {
    ".py": "python",
    ".js": "js", ".jsx": "js", ".mjs": "js", ".cjs": "js",
    ".ts": "ts", ".tsx": "ts",
    ".java": "java",
    ".go": "go",
    ".rs": "rust",
    ".rb": "ruby",
    ".php": "php",
    ".c": "c",
    ".h": "cpp", ".hpp": "cpp", ".cpp": "cpp", ".cc": "cpp",
    ".cs": "csharp",
    ".md": "markdown", ".markdown": "markdown",
    ".rst": "rst",
}
ALLOWED_EXTENSIONS = set(EXTENSION_LANGUAGE_MAP.keys())

SKIP_DIR_NAMES = {
    "node_modules", "venv", ".venv", "dist", "build", ".git",
    "__pycache__", ".tox", "vendor", "target", ".mypy_cache",
}
SKIP_FILE_PATTERNS = {
    "package-lock.json", "yarn.lock", "poetry.lock", "Pipfile.lock",
    "Cargo.lock", "go.sum",
}
MINIFIED_MARKER = ".min."  # e.g. "app.min.js" — skipped regardless of extension
DOCS_DIR_NAME = "docs"
CANONICAL_DOCS_LANG = "en"  # if docs/en/ exists, index only it — see file_walker.py

# --- Chunking ---
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200

# --- Embedding ---
EMBEDDING_BATCH_SIZE = 100
EMBEDDING_MAX_RETRIES = 3
EMBEDDING_COST_PER_1M_TOKENS = 0.02  # text-embedding-3-small, verify against OpenAI's pricing page
EMBEDDING_MAX_INPUT_TOKENS = 8000  # API hard limit is 8192; margin for tokenizer edge cases

# --- Vector store ---
CODE_COLLECTION_NAME = "code"
HISTORY_COLLECTION_NAME = "history"
CHROMA_ADD_BATCH_SIZE = 1000  # stay well under Chroma's internal max_batch_size

# --- Retrieval ---
TOP_K = 5
RRF_K = 60
RRF_CANDIDATE_POOL = 20  # results fetched from each ranking before fusion, then cut to top_k
RETRIEVAL_MODE = "hybrid"  # "dense" | "bm25" | "hybrid" — evaluate.py overrides per config

# --- Query optimization ---
QUERY_OPTIMIZER_MAX_RETRIES = 3

# --- Reranking ---
RERANK_CANDIDATE_POOL = 20  # candidates fetched (post-fusion) before reranking, then cut to top_k
RERANK_MAX_RETRIES = 3

# --- History indexing ---
MAX_COMMITS = 2000
HISTORY_PR_SCAN_LIMIT = 2000  # merged PRs scanned when building the sha -> PR join map
GITHUB_MAX_RETRIES = 3
FILES_TOUCHED_DELIMITER = "|"  # Chroma metadata can't hold lists; encode files_touched as "|a|b|c|"

# --- Eval set construction ---
EVAL_MIN_MERGED_PRS = 100
EVAL_MIN_DESCRIPTION_CHARS = 50
EVAL_MAX_FILES_TOUCHED = 3
EVAL_MIN_FILES_TOUCHED = 1
EVAL_TARGET_SIZE = 150  # stop scanning once this many qualifying items are found
EVAL_PR_SCAN_LIMIT = 800  # hard cap on merged PRs scanned looking for qualifying items

# --- Agent ---
MAX_ITERATIONS = 6
MAX_TOOL_OUTPUT_CHARS = 2000

# --- Cost guardrail ---
COST_CONFIRMATION_THRESHOLD_USD = 1.0

# --- API ---
API_HOST = "0.0.0.0"
API_PORT = 8000
