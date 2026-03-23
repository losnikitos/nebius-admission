# Nebius Admission: AI Performance Engineering 2026 (Stub)

This repository currently contains a minimal FastAPI server that exposes the required `POST /summarize` endpoint, but does not fetch or summarize GitHub repositories yet.

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

## Run the server

- `uvicorn app.main:app --host 0.0.0.0 --port 8000`

## Verify the endpoint

Run:

```bash
curl -X POST http://localhost:8000/summarize \
  -H "Content-Type: application/json" \
  -d '{"github_url": "https://github.com/psf/requests"}'
```

Expected response (stub):

```json
{
  "summary": "OK",
  "technologies": [],
  "structure": "Stub: endpoint is wired but repo fetching/summarization is not implemented yet."
}
```

