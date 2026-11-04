"""Unit tests for DocuMind API health and session lifecycle."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_health_endpoints(client: TestClient) -> None:
    """Verifies /health and /api/v1/health endpoints."""
    resp1 = client.get("/health")
    assert resp1.status_code == 200
    assert resp1.json()["status"] == "ok"
    assert "embed_model" in resp1.json()

    resp2 = client.get("/api/v1/health")
    assert resp2.status_code == 200
    assert resp2.json()["status"] == "ok"


def test_session_lifecycle_crud(client: TestClient) -> None:
    """Tests creating, listing, retrieving, renaming, and deleting sessions."""
    headers = {"X-Client-Token": "test-user-token-1"}

    # 1. Create session
    resp = client.post("/api/v1/sessions", json={"name": "ML Research"}, headers=headers)
    assert resp.status_code == 201
    s_data = resp.json()
    session_id = s_data["id"]
    assert s_data["name"] == "ML Research"
    assert s_data["chunk_count"] == 0

    # 2. List sessions
    list_resp = client.get("/api/v1/sessions", headers=headers)
    assert list_resp.status_code == 200
    assert any(s["id"] == session_id for s in list_resp.json()["sessions"])

    # 3. Get session detail
    detail_resp = client.get(f"/api/v1/sessions/{session_id}", headers=headers)
    assert detail_resp.status_code == 200
    assert detail_resp.json()["id"] == session_id

    # 4. Rename session
    patch_resp = client.patch(
        f"/api/v1/sessions/{session_id}",
        json={"name": "Deep Learning Papers"},
        headers=headers,
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["name"] == "Deep Learning Papers"

    # 5. Delete session
    del_resp = client.delete(f"/api/v1/sessions/{session_id}", headers=headers)
    assert del_resp.status_code == 204

    # 6. Verify 404 after deletion
    not_found_resp = client.get(f"/api/v1/sessions/{session_id}", headers=headers)
    assert not_found_resp.status_code == 404
