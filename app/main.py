import re
from typing import List

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field


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

    # No fetching / parsing / LLM calls yet (stub mode).
    return SummarizeResponse(
        summary="OK",
        technologies=[],
        structure="Stub: endpoint is wired but repo fetching/summarization is not implemented yet.",
    )

