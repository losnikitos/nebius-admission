# Nebius Admission: AI Performance Engineering 2026 (Stub)

This repository currently contains a minimal FastAPI server that exposes the required `POST /summarize` endpoint and fetches a filename-only repo tree from GitHub (summarization/LLM comes next).

## Model selection (for the future LLM implementation)

Planned provider: **Nebius Token Factory API**.

Planned model: `meta-llama/Meta-Llama-3.1-8B-Instruct` (chosen as a general-purpose instruction-tuned model for codebase summarization; will be used once the LLM wiring is implemented).

## Setup

1. Create and activate a virtual environment:
   - `python3 -m venv .venv`
   - `source .venv/bin/activate`

2. Install dependencies:
   - `pip install -r requirements.txt`

3. Set the LLM API key environment variable (not used by the current stub, but required for the non-stub implementation):
   - `export NEBIUS_API_KEY="your_key_here"`
4. (Optional but recommended) Set a GitHub token to reduce rate limiting when fetching repo trees:
   - `export GITHUB_TOKEN="your_github_token_here"`

## Run the server

- `uvicorn app.main:app --host 0.0.0.0 --port 8000`

## Endpoints

### `POST /summarize`
Accepts a JSON body and returns an LLM-generated summary.

```bash
curl -X POST http://localhost:8000/summarize \
  -H "Content-Type: application/json" \
  -d '{"github_url": "https://github.com/psf/requests"}'
```

### `GET /summarize/{owner}/{repo}`
Browser-friendly equivalent of `POST /summarize`.

```
http://localhost:8000/summarize/psf/requests
```

### `GET /prompt/{owner}/{repo}`
Debug endpoint — returns the exact system and user prompts that would be sent to the LLM, without calling it.

```
http://localhost:8000/prompt/psf/requests
```

All three endpoints return the same error shape on failure:

```json
{"status": "error", "message": "..."}
```

