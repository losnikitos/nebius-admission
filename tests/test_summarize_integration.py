import sys
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

# Ensure the project root is on `sys.path` so `import app` works when running `pytest`.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT))

from app.main import app


def test_post_summarize_returns_200() -> None:
    client = TestClient(app)

    # Avoid relying on network access in unit tests.
    with patch(
        "app.main.fetch_repo_file_paths",
        return_value=[
            "README.md",
            "pyproject.toml",
            "src/requests/__init__.py",
            "tests/test_requests.py",
            ".github/workflows/ci.yml",
        ],
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

