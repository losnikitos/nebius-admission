import sys
from pathlib import Path

from fastapi.testclient import TestClient

# Ensure the project root is on `sys.path` so `import app` works when running `pytest`.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT))

from app.main import app


def test_post_summarize_returns_200() -> None:
    client = TestClient(app)
    response = client.post(
        "/summarize",
        json={"github_url": "https://github.com/psf/requests"},
    )

    assert response.status_code == 200

    payload = response.json()
    assert payload["summary"] == "OK"
    assert isinstance(payload["technologies"], list)
    assert "structure" in payload

