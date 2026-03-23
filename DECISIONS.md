## Design Decisions Log

### 2026-03-23: Use FastAPI
- Decision: Use FastAPI with typed Pydantic request/response models.
- Why: Clear contract and straightforward unit/integration testing via `TestClient`.

### 2026-03-23: GitHub fetching via client library
- Decision: Use `PyGithub` to fetch the repo file tree (filenames only).
- Why: Avoid raw GitHub HTTP and reuse client auth/rate-limit handling.

### 2026-03-23: Parse `github_url`
- Decision: Parse `https://github.com/<owner>/<repo>` via regex.
- Why: Deterministic validation for this stage (public repos only).

### 2026-03-23: Filenames-only “structure”
- Decision: Return a truncated filename tree in `structure`; do not fetch contents yet.
- Why: Keeps context small until the LLM content-selection step is added.

### 2026-03-23: Filtering + truncation
- Decision: Exclude obvious binaries/vendor/lock artifacts and cap at `max_files=200` (sorted).
- Why: Reduce noise and prevent context blow-ups later.

### 2026-03-23: Repo filter config format
- Decision: Store filter + extension heuristics in `repo_filter_config.toml` (TOML).
- Why: No extra dependencies; editability without code changes.

### 2026-03-23: Optional GitHub token
- Decision: If `GITHUB_TOKEN` is set, pass it to `PyGithub`; otherwise use unauthenticated access.
- Why: Lower rate limits without making the token mandatory for tests.

### 2026-03-23: Technologies inference is heuristic
- Decision: Infer `technologies` from file extensions.
- Why: Works with filenames-only input.

### 2026-03-23: Error mapping
- Decision: Map fetch failures to HTTP `404/403/422/502` and return `{status,message}` JSON.
- Why: Make failures explicit and easy to test/consume.

### 2026-03-23: Tests avoid network
- Decision: Mock `fetch_repo_file_paths` in integration tests.
- Why: Prevent CI flakiness from GitHub/network variability.

### 2026-03-23: Technologies inference config
- Decision: Move extension-to-technology inference into the same repo-filter config.
- Why: Keep repo heuristics centralized and editable without touching code.

### 2026-03-23: Fetch repo metadata alongside file tree
- Decision: `fetch_repo_context` returns `RepoContext(metadata, paths)` where `metadata` holds `description`, `topics`, `languages` (lang→LoC bytes), `default_branch`, `homepage`, and `stars` from the GitHub repo and languages API endpoints.
- Why: These fields are high-signal for LLM summarization and cheap to fetch with the same PyGithub `repo` object already in hand. Topics and language breakdown directly answer "what does this do" and "what technologies are used".
