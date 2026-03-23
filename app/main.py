import re
from typing import List

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.github_repo_fetcher import (
    RepoEmptyError,
    RepoNotFoundError,
    RepoUnauthorizedError,
    fetch_repo_file_paths,
    guess_technologies_from_paths,
    make_structure_tree,
)


app = FastAPI(title="Nebius Admission Summarizer (stub)")


class SummarizeRequest(BaseModel):
    github_url: str = Field(..., description="Public GitHub repository URL")


class SummarizeResponse(BaseModel):
    summary: str
    technologies: List[str]
    structure: str


_GITHUB_REPO_URL_RE = re.compile(
    r"^https?://github\.com/"
    r"(?P<owner>[A-Za-z0-9_.-]+)/"
    r"(?P<repo>[A-Za-z0-9_.-]+)"
    r"(?:\.git)?/?$"
)


def _github_repo_url_is_valid(url: str) -> bool:
    return _GITHUB_REPO_URL_RE.match(url.strip()) is not None


@app.post("/summarize", response_model=SummarizeResponse)
def summarize(payload: SummarizeRequest) -> SummarizeResponse | JSONResponse:
    """
    Stub implementation:
    - validates `github_url` format
    - returns a static OK response
    """
    if not _github_repo_url_is_valid(payload.github_url):
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": "Invalid github_url"},
        )

    try:
        paths = fetch_repo_file_paths(payload.github_url, max_files=200)
        technologies = guess_technologies_from_paths(paths)
        structure = make_structure_tree(paths)
    except RepoNotFoundError as e:
        return JSONResponse(
            status_code=404,
            content={"status": "error", "message": f"Repository not found: {e}"},
        )
    except RepoUnauthorizedError as e:
        return JSONResponse(
            status_code=403,
            content={"status": "error", "message": f"Unauthorized access: {e}"},
        )
    except RepoEmptyError as e:
        return JSONResponse(
            status_code=422,
            content={"status": "error", "message": f"Empty repository: {e}"},
        )
    except Exception as e:
        # Covers network errors, rate limiting, GitHub API failures, etc.
        return JSONResponse(
            status_code=502,
            content={"status": "error", "message": f"Failed to fetch repository: {e}"},
        )

    # Next step will be LLM summarization using filenames + (later) selective contents.
    # For now, we provide a deterministic placeholder summary based on the fetched tree.
    return SummarizeResponse(
        summary="Fetched repository file tree; LLM summarization comes next.",
        technologies=technologies,
        structure=structure,
    )

