from typing import List

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app.github_repo_fetcher import (
    RepoEmptyError,
    RepoNotFoundError,
    RepoUnauthorizedError,
    fetch_repo_context,
    parse_github_repo_url,
)
from app.llm_client import summarize_repo


app = FastAPI(title="Nebius Admission Summarizer (stub)")


class SummarizeRequest(BaseModel):
    github_url: str = Field(..., description="Public GitHub repository URL")


class SummarizeResponse(BaseModel):
    summary: str
    technologies: List[str]
    structure: str


@app.post("/summarize", response_model=SummarizeResponse)
def summarize(payload: SummarizeRequest) -> SummarizeResponse:
    try:
        parse_github_repo_url(payload.github_url)
    except ValueError:
        raise HTTPException(status_code=400, detail={"status": "error", "message": "Invalid github_url"})

    try:
        ctx = fetch_repo_context(payload.github_url, max_files=200)
    except RepoNotFoundError as e:
        raise HTTPException(status_code=404, detail={"status": "error", "message": f"Repository not found: {e}"})
    except RepoUnauthorizedError as e:
        raise HTTPException(status_code=403, detail={"status": "error", "message": f"Unauthorized access: {e}"})
    except RepoEmptyError as e:
        raise HTTPException(status_code=422, detail={"status": "error", "message": f"Empty repository: {e}"})
    except Exception as e:
        raise HTTPException(status_code=502, detail={"status": "error", "message": f"Failed to fetch repository: {e}"})

    try:
        summary, technologies, structure = summarize_repo(ctx)
    except ValueError as e:
        raise HTTPException(status_code=502, detail={"status": "error", "message": f"LLM returned invalid response: {e}"})
    except Exception as e:
        raise HTTPException(status_code=502, detail={"status": "error", "message": f"LLM request failed: {e}"})

    return SummarizeResponse(
        summary=summary,
        technologies=technologies,
        structure=structure,
    )

