import importlib

import pytest


fastapi = pytest.importorskip("fastapi")
pytest.importorskip("multipart")
from fastapi.testclient import TestClient


service_api = importlib.import_module("api.app")
client = TestClient(service_api.app)


def test_health_endpoint_returns_ok():
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "document-verification-api"


def test_submit_task_returns_task_metadata(monkeypatch):
    monkeypatch.setattr(service_api, "_submit_verification_task", lambda task_id: None)

    response = client.post(
        "/api/v1/tasks/verify",
        files={"file": ("sample.pdf", b"%PDF-1.4 fake content", "application/pdf")},
        data={"api_key": "test-key"},
    )

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "pending"
    assert body["filename"] == "sample.pdf"
    assert body["task_id"]


def test_submit_task_dry_run_completes_immediately():
    response = client.post(
        "/api/v1/tasks/verify",
        files={"file": ("sample.pdf", b"%PDF-1.4 fake content", "application/pdf")},
        data={"dry_run": "true"},
    )

    assert response.status_code == 202
    body = response.json()
    assert body["dry_run"] is True
    assert body["status"] == "completed"

    task_id = body["task_id"]
    status = client.get(f"/api/v1/tasks/{task_id}")
    assert status.status_code == 200
    assert status.json()["status"] == "completed"

    report = client.get(f"/api/v1/tasks/{task_id}/report")
    assert report.status_code == 200
    assert "Dry Run Verification Report" in report.json()["report"]
