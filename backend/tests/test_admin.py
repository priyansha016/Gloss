"""Admin stats and public showcase endpoints."""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import router
from app.config import get_settings


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("ADMIN_SECRET", "test-admin-secret")
    get_settings.cache_clear()
    app = FastAPI()
    app.include_router(router)
    yield TestClient(app)
    get_settings.cache_clear()


def test_admin_disabled_without_secret(monkeypatch):
    monkeypatch.delenv("ADMIN_SECRET", raising=False)
    get_settings.cache_clear()
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as c:
        r = c.get("/api/admin/stats", headers={"X-Admin-Key": "anything"})
        assert r.status_code == 404
    get_settings.cache_clear()


def test_admin_rejects_wrong_key(client):
    r = client.get("/api/admin/stats", headers={"X-Admin-Key": "wrong"})
    assert r.status_code == 401


@patch("app.api.routes.get_llm_usage", new_callable=AsyncMock, return_value=(12, 3400))
@patch("app.api.routes._load_showcase_videos", new_callable=AsyncMock, return_value=[])
@patch("app.api.routes.get_db")
def test_admin_stats_shape(mock_get_db, _showcase, _usage, client):
    mock_db = AsyncMock()
    mock_get_db.return_value.__aenter__ = AsyncMock(return_value=mock_db)
    mock_get_db.return_value.__aexit__ = AsyncMock(return_value=None)

    status_result = AsyncMock()
    status_result.all.return_value = []
    job_result = AsyncMock()
    job_result.all.return_value = []
    mock_db.execute = AsyncMock(side_effect=[status_result, job_result])

    r = client.get("/api/admin/stats", headers={"X-Admin-Key": "test-admin-secret"})
    assert r.status_code == 200
    body = r.json()
    assert body["llm_calls"] == 12
    assert body["llm_tokens"] == 3400
    assert "videos_total" in body


@patch("app.api.routes._load_showcase_videos", new_callable=AsyncMock)
def test_showcase_public(mock_load, client):
    vid = uuid.uuid4()
    video = type(
        "V",
        (),
        {
            "id": vid,
            "youtube_id": "abc123",
            "title": "Demo",
            "channel": "Ch",
            "duration_s": 600,
        },
    )()
    mock_load.return_value = [video]
    r = client.get("/api/showcase")
    assert r.status_code == 200
    assert r.json()[0]["id"] == str(vid)
