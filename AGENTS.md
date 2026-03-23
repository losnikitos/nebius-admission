## Task Requirements: AI Performance Engineering 2026 (Admission Assignment)

You are a coding agent implementing the “AI Performance Engineering 2026” admission task as described below.

### Goal
Build a simple Python API service that:
1. Accepts a GitHub repository URL.
2. Fetches and filters repository contents.
3. Uses an LLM to generate a human-readable summary describing:
   - what the project does,
   - what technologies are used,
   - how the project is structured.

### Tech & Runtime Constraints
1. Language: **Python 3.10+**
2. Web framework: **FastAPI or Flask** (choose one)
3. LLM:
   - Primary: **Nebius Token Factory API**
   - Alternative: **Any other LLM provider** (OpenAI / Anthropic / Gemini, etc.)
4. Model selection:
   - If using Nebius Token Factory: choose a model available there.
   - If using an alternative provider: choose a model supported by that provider.
   - You must choose one model and justify it briefly (1–2 sentences) in `README.md`.

### LLM API Key Handling (Non-Negotiable)
1. LLM API key is provided via an environment variable.
2. Do not hardcode API keys in source code or config files.
3. For Nebius Token Factory, use `NEBIUS_API_KEY`.
4. If using an alternative provider, use the provider’s conventional environment variable name (e.g. `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, etc.).

### API Endpoint Specification
Implement the following endpoint:

#### `POST /summarize`
Request body (JSON):
```json
{
  "github_url": "https://github.com/psf/requests"
}
```

Behavior:
1. Validate that `github_url` is present and is a URL of a **public** GitHub repository.
2. Fetch repository contents from the provided URL.
3. Filter repository files so the LLM receives the most informative content while avoiding oversized/binary/irrelevant files.
4. Use the LLM to generate a response in the required schema.

Response (JSON):
```json
{
  "summary": "Human-readable description of what the project does",
  "technologies": ["List of main technologies/languages/frameworks"],
  "structure": "Brief description of the project structure"
}
```

Error response:
1. Return an appropriate HTTP status code.
2. Return JSON shaped as:
```json
{
  "status": "error",
  "message": "Description of what went wrong"
}
```

At minimum, handle:
- invalid request payload (missing/invalid `github_url`)
- network errors when fetching the repo
- private repo / unauthorized access
- empty or unparseable repositories

### Repo Processing Requirements (Key Challenge)
You must implement a sensible strategy for selecting what to include for the LLM.
In particular:
1. Repositories can be large: do not send everything to the LLM.
2. Skip files that are typically not helpful or unsafe for LLM context, such as:
   - binary files,
   - lock files where appropriate,
   - large/minified files when appropriate,
   - directories like `node_modules/`,
   - other obviously irrelevant content.
3. Decide how to prioritize informative content. Prefer, for example:
   - `README*` and top-level docs,
   - directory tree / structure hints,
   - key source files (e.g., entrypoints, core modules),
   - configuration files (e.g., build/test/lint configs),
   - tests (when present).
4. Handle LLM context window limits:
   - implement truncation and/or summarization,
   - prioritize the most informative parts first,
   - ensure the solution does not crash for large repos.

There is no single “correct” approach; your implementation should reflect clear reasoning and be robust.

### Prompt Engineering Requirements
1. Use clear prompts that instruct the LLM to output structured content matching the required response schema.
2. The LLM output should be easy to parse/validate (you may enforce formatting and/or post-process).
3. Ensure the produced fields (`summary`, `technologies`, `structure`) are useful and consistent.

### How Your Code Must Run (Evaluation Procedure)
During evaluation, the system will follow your `README.md` instructions on a clean machine:
1. Your `README.md` must contain **step-by-step** instructions to:
   - install dependencies,
   - start the server,
   - verify that the `POST /summarize` endpoint exists and responds correctly.
2. After following the instructions, the server must listen and expose `POST /summarize`.
3. The evaluator will test using:
```bash
curl -X POST http://localhost:8000/summarize \
  -H "Content-Type: application/json" \
  -d '{"github_url": "https://github.com/psf/requests"}'
```
4. Ensure the LLM API key is read from `NEBIUS_API_KEY` (or the equivalent env var for your chosen alternative provider).
5. Do not hardcode keys.

### What to Submit
Submit a zip archive containing:
1. `README.md` (must include all required information described above)
2. The working application code and dependency files so the evaluator can run it as documented.

### Evaluation Criteria (What Will Be Scored)
Blocking criteria (must pass; otherwise score is 0):
1. The server starts following `README.md` instructions.
2. The `POST /summarize` endpoint exists and accepts the specified request format.
3. The endpoint returns a response (not an error) for a valid public GitHub repository.
4. An LLM API is actually used (Nebius Token Factory or an alternative provider).

Scoring (100 total, partial credit allowed):
1. Functionality (20): endpoint returns a meaningful summary; response matches schema.
2. Repo processing (20): files filtered sensibly; clear strategy for selecting informative files.
3. Context management (20): handles large repos without crashing or overwhelming the LLM context window.
4. Prompt engineering (10): prompts are clear and produce structured, useful output.
5. Code quality & error handling (20): readable/organized code; edge cases handled; no hardcoded keys.
6. Documentation (10): README includes working setup instructions and brief design decisions.

### Agent Operating Constraints
1. Prefer a clean, minimal implementation that works reliably over a highly complex one.
2. Keep code readable and ensure robust error handling paths.
3. Ensure outputs conform to the specified JSON schema.

