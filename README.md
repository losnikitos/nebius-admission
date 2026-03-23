# GitHub Repository Summarizer

A FastAPI service that accepts a GitHub repository URL and returns an LLM-generated summary of what the project does, what technologies it uses, and how it is structured.

## Model choice

**Provider:** Nebius Token Factory API
**Model:** `Qwen/Qwen3-30B-A3B-Instruct-2507`

Cross-checked https://artificialanalysis.ai/leaderboards/models vs Nebius pricing https://nebius.com/token-factory/prices, filtered models with tool calls, no need for media recognition or generation. Found a most cost effective one.

## Setup

### 1. Prerequisites

- Python 3.10 or later
- A Nebius API key (required)
- A GitHub personal access token (optional, but recommended to avoid rate limiting)

### 2. Clone and create a virtual environment

```bash
git clone <repo-url>
cd nebius-admission
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Set environment variables

**Required:**
```bash
export NEBIUS_API_KEY="your_nebius_api_key_here"
```

**Optional** (raises GitHub API rate limit from 60 to 5000 requests/hour):
```bash
export GITHUB_TOKEN="your_github_personal_access_token"
```

The `GITHUB_TOKEN` is not required for the service to work — unauthenticated access is used when it is absent.

### 5. Start the server

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Endpoints

### `POST /summarize` (canonical)

Accepts a JSON body with a public GitHub repository URL and returns an LLM-generated analysis.

**Request:**
```bash
curl -X POST http://localhost:8000/summarize \
  -H "Content-Type: application/json" \
  -d '{"github_url": "https://github.com/psf/requests"}'
```

**Success response (200):**
```json
{
  "summary": "Human-readable description of what the project does",
  "technologies": ["Python", "pytest", "GitHub Actions"],
  "structure": "Brief description of the project structure"
}
```

**Error response:**
```json
{
  "status": "error",
  "message": "Description of what went wrong"
}
```

Handled error cases and their HTTP status codes:

| Situation | Status |
|---|---|
| Missing or malformed `github_url` | 422 |
| Private repo / unauthorized access | 403 |
| Repository not found | 404 |
| Network / GitHub API failure | 502 |
| Empty or unparseable repository | 422 |

---

### `GET /summarize/{owner}/{repo}` (convenience)

Browser-friendly equivalent of `POST /summarize`. Useful for quick manual testing without curl.

```
http://localhost:8000/summarize/psf/requests
```

Returns the same response shape as the POST endpoint.

---

### `GET /prompt/{owner}/{repo}` (debug)

Returns the exact system and user prompts that would be sent to the LLM, without actually calling it. Useful for inspecting what context is being built for a given repository.

```
http://localhost:8000/prompt/psf/requests
```

**Response:**
```json
{
  "system_prompt": "...",
  "user_prompt": "..."
}
```

---

## Repository processing strategy

The service applies a multi-stage filtering and prioritization pipeline before passing content to the LLM:

1. **Skip noise** — binary files, lock files (`*.lock`, `package-lock.json`, …), minified JS/CSS, vendored directories (`node_modules/`, `.venv/`, `vendor/`, …), and build artefacts are excluded. Rules are driven by `app/repo_filter_config.toml`.
2. **Fetch metadata** — repository description, topics, language breakdown (bytes), homepage, and default branch are fetched cheaply from the GitHub API and always included.
3. **Prioritize key files** — README files and top-level docs are fetched in full first, followed by configuration files (pyproject.toml, Makefile, Dockerfile, …) and entry-point source files.
4. **Context cap** — total file content is capped so the prompt stays within the model's context window. The most informative files (by priority tier and size) are included first.
5. **Agentic loop** — the LLM receives an initial prompt with metadata, the root directory listing, and key file contents. It can then call `ls(directory)` or `cat(path)` tools to fetch additional files it needs, up to a configurable turn limit, before calling `answer()` with the final structured result.

## Interactive API docs

With the server running, visit:

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
