from typing import List

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app.github_repo_fetcher import (
    RepoEmptyError,
    RepoNotFoundError,
    RepoUnauthorizedError,
    fetch_repo_file_paths,
    guess_technologies_from_paths,
    make_structure_tree,
    parse_github_repo_url,
)


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
        paths = fetch_repo_file_paths(payload.github_url, max_files=200)
        technologies = guess_technologies_from_paths(paths)
        structure = make_structure_tree(paths)
    except RepoNotFoundError as e:
        raise HTTPException(status_code=404, detail={"status": "error", "message": f"Repository not found: {e}"})
    except RepoUnauthorizedError as e:
        raise HTTPException(status_code=403, detail={"status": "error", "message": f"Unauthorized access: {e}"})
    except RepoEmptyError as e:
        raise HTTPException(status_code=422, detail={"status": "error", "message": f"Empty repository: {e}"})
    except Exception as e:
        raise HTTPException(status_code=502, detail={"status": "error", "message": f"Failed to fetch repository: {e}"})

    # Next step will be LLM summarization using filenames + (later) selective contents.
    # For now, we provide a deterministic placeholder summary based on the fetched tree.
    return SummarizeResponse(
        summary="Fetched repository file tree; LLM summarization comes next.",
        technologies=technologies,
        structure=structure,
    )

