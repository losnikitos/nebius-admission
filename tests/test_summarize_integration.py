from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.github_repo_fetcher import RepoContext, RepoMetadata


_FAKE_PATHS = [
    "README.md",
    "pyproject.toml",
    "src/requests/__init__.py",
    "tests/test_requests.py",
    ".github/workflows/ci.yml",
]

_FAKE_CONTEXT = RepoContext(
    metadata=RepoMetadata(
        description="A simple, yet elegant, HTTP library.",
        topics=["http", "python", "requests"],
        languages={"Python": 500000, "Shell": 1000},
        default_branch="main",
        homepage="https://requests.readthedocs.io",
        stars=52000,
    ),
    paths=_FAKE_PATHS,
)


def test_post_summarize_returns_200() -> None:
    client = TestClient(app)

    # Avoid relying on network access in unit tests.
    with patch("app.main.fetch_repo_context", return_value=_FAKE_CONTEXT):
        response = client.post(
            "/summarize",
            json={"github_url": "https://github.com/psf/requests"},
        )

    assert response.status_code == 200

    payload = response.json()
    assert isinstance(payload["summary"], str)
    assert isinstance(payload["technologies"], list)
    assert "structure" in payload

