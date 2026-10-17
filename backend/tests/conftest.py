import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_TODAY", "2026-10-17")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "t.db"))
    monkeypatch.setenv("CACHE_DIR", str(tmp_path / "cache"))
    for k in ("GEMINI_API_KEY", "SARVAM_API_KEY", "DATA_GOV_API_KEY", "ML_ENABLED", "GEMINI_SCHEMA_STYLE"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("OPEN_METEO_URL", "http://mock/v1/forecast")
    import httpx
    from config import reset_settings
    from integrations import http, market, weather
    from tests import mock_providers
    reset_settings()
    http.set_transport(httpx.ASGITransport(app=mock_providers.app))
    weather._CACHE.clear(); market._CACHE.clear()
    mock_providers.STT_QUEUE.clear(); mock_providers.LLM_QUEUE.clear(); mock_providers.LOG.clear()
    mock_providers.FLAGS["reject_response_format"] = False
    yield
    http.set_transport(None)
    reset_settings()


@pytest.fixture
def with_keys(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini")
    monkeypatch.setenv("SARVAM_API_KEY", "test-sarvam")
    monkeypatch.setenv("GEMINI_BASE_URL", "http://mock")
    monkeypatch.setenv("SARVAM_BASE_URL", "http://mock")
    from config import reset_settings
    reset_settings()
    yield


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    from main import app
    with TestClient(app) as c:
        yield c
