from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.github_repo_fetcher import KeyFileContent, RepoContext, RepoMetadata


_FAKE_DATA = RepoContext(
    metadata=RepoMetadata(
        description="A simple, yet elegant, HTTP library.",
        topics=["http", "python", "requests"],
        languages={"Python": 500000, "Shell": 1000},
        default_branch="main",
        homepage="https://requests.readthedocs.io",
        stars=32000,
    ),
    paths=["README.md", "pyproject.toml", "src/requests/__init__.py", "tests/test_utils.py"],
    key_files_content=[
        KeyFileContent(name="README.md", content="# Requests\nHTTP for Humans."),
        KeyFileContent(name="pyproject.toml", content='[project]\nname = "requests"'),
    ],
    owner="psf",
    repo_name="requests",
    commit_sha="abc123",
)

_FAKE_SUMMARY = (
    "requests is a popular HTTP library for Python.",
    ["Python", "HTTP"],
    "The project has a src layout with tests alongside the source.",
)

def test_post_summarize_returns_200() -> None:
    client = TestClient(app)

    with (
        patch("app.main.fetch_repo_context", return_value=_FAKE_DATA),
        patch("app.main.summarize_repo", return_value=_FAKE_SUMMARY),
    ):
        response = client.post(
            "/summarize",
            json={"github_url": "https://github.com/psf/requests"},
        )

    assert response.status_code == 200

    payload = response.json()
    assert isinstance(payload["summary"], str)
    assert isinstance(payload["technologies"], list)
    assert "structure" in payload
