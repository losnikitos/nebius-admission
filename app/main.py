import logging
from typing import List

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
from pydantic import BaseModel, Field

from app.github_repo_fetcher import (
    RepoEmptyError,
    RepoNotFoundError,
    RepoUnauthorizedError,
    fetch_repo_context,
    parse_github_repo_url,
)
from app.llm_client import summarize_repo, build_prompt, _SYSTEM_PROMPT


app = FastAPI(title="Nebius Admission Summarizer (stub)")


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    detail = exc.detail
    if not isinstance(detail, dict):
        detail = {"status": "error", "message": str(detail)}
    return JSONResponse(status_code=exc.status_code, content=detail)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={"status": "error", "message": f"Invalid request: {exc}"},
    )


class SummarizeRequest(BaseModel):
    github_url: str = Field(..., description="Public GitHub repository URL")


class SummarizeResponse(BaseModel):
    summary: str
    technologies: List[str]
    structure: str


def _summarize_url(github_url: str) -> SummarizeResponse:
    try:
        parse_github_repo_url(github_url)
    except ValueError:
        raise HTTPException(status_code=400, detail={"status": "error", "message": "Invalid github_url"})

    try:
        ctx = fetch_repo_context(github_url, max_files=200)
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

    return SummarizeResponse(summary=summary, technologies=technologies, structure=structure)


@app.get("/prompt/{owner}/{repo}")
def prompt_debug(owner: str, repo: str) -> dict:
    github_url = f"https://github.com/{owner}/{repo}"
    try:
        parse_github_repo_url(github_url)
    except ValueError:
        raise HTTPException(status_code=400, detail={"status": "error", "message": "Invalid repository"})

    try:
        ctx = fetch_repo_context(github_url, max_files=200)
    except RepoNotFoundError as e:
        raise HTTPException(status_code=404, detail={"status": "error", "message": f"Repository not found: {e}"})
    except RepoUnauthorizedError as e:
        raise HTTPException(status_code=403, detail={"status": "error", "message": f"Unauthorized access: {e}"})
    except RepoEmptyError as e:
        raise HTTPException(status_code=422, detail={"status": "error", "message": f"Empty repository: {e}"})
    except Exception as e:
        raise HTTPException(status_code=502, detail={"status": "error", "message": f"Failed to fetch repository: {e}"})

    return {
        "system_prompt": _SYSTEM_PROMPT,
        "user_prompt": build_prompt(ctx),
    }


@app.get("/summarize/{owner}/{repo}", response_model=SummarizeResponse)
def summarize_get(owner: str, repo: str) -> SummarizeResponse:
    return _summarize_url(f"https://github.com/{owner}/{repo}")


@app.post("/summarize", response_model=SummarizeResponse)
def summarize(payload: SummarizeRequest) -> SummarizeResponse:
    return _summarize_url(payload.github_url)

