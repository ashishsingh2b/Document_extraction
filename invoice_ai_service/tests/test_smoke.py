"""Smoke tests — lightweight API wiring (no full OCR stack required)."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import training as training_routes
from app.config import settings as settings_mod


def _training_app() -> FastAPI:
    app = FastAPI()
    app.include_router(training_routes.router, prefix="/api/v1")
    return app


def test_training_router_registered():
    client = TestClient(_training_app())
    spec = client.get("/openapi.json").json()
    assert "/api/v1/train" in spec["paths"]


def test_train_post_rejects_when_secret_required(monkeypatch):
    settings_mod.reload_settings()
    monkeypatch.setattr(settings_mod.settings, "TRAIN_API_SECRET", "test-secret-xyz", raising=False)

    client = TestClient(_training_app())
    assert client.post("/api/v1/train").status_code == 401
    assert (
        client.post("/api/v1/train", headers={"X-Training-Secret": "wrong"}).status_code
        == 401
    )


def test_train_post_accepts_correct_secret(monkeypatch):
    settings_mod.reload_settings()
    monkeypatch.setattr(settings_mod.settings, "TRAIN_API_SECRET", "correct", raising=False)

    client = TestClient(_training_app())
    r = client.post("/api/v1/train", headers={"X-Training-Secret": "correct"})
    assert r.status_code in (200, 500)


@pytest.mark.integration
def test_full_app_imports():
    pytest.importorskip("PIL")
    pytest.importorskip("fitz", reason="PyMuPDF")
    from app.main import app

    assert app.title
    client = TestClient(app)
    assert client.get("/").status_code == 200
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/v1/upload" in paths
