from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.repo_data import RepoData, KeyFileContent


_FAKE_DATA = RepoData(
    owner="psf",
    repo_name="requests",
    description="A simple, yet elegant, HTTP library.",
    topics=["http", "python", "requests"],
    languages={"Python": 500000, "Shell": 1000},
    homepage="https://requests.readthedocs.io",
    root_files=["README.md", "pyproject.toml", "src/", "tests/", ".github/"],
    key_files_content=[
        KeyFileContent(name="README.md", content="# Requests\nHTTP for Humans."),
        KeyFileContent(name="pyproject.toml", content='[project]\nname = "requests"'),
    ],
)

_FAKE_SUMMARY = (
    "requests is a popular HTTP library for Python.",
    ["Python", "HTTP"],
    "The project has a src layout with tests alongside the source.",
)

def test_post_summarize_returns_200() -> None:
    client = TestClient(app)

    with (
        patch("app.main.fetch_repo_data", return_value=_FAKE_DATA),
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
