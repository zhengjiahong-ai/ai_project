"""Tests for the /api/health endpoint."""
import json

import pytest

pytest.importorskip("fastapi", reason="FastAPI not available")


def _client():
    """Build a FastAPI TestClient with the health router mounted."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routes.health import router

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_health_returns_200():
    client = _client()
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert "status" in body
    assert "checks" in body
    assert "uptime_seconds" in body
    assert isinstance(body["uptime_seconds"], (int, float))


def test_health_checks_have_grobid_and_rag():
    client = _client()
    body = client.get("/health").json()
    assert "grobid" in body["checks"]
    assert "rag" in body["checks"]
    for key in ("grobid", "rag"):
        check = body["checks"][key]
        assert check["status"] in ("ok", "degraded", "unavailable")
        assert isinstance(check["message"], str)


def test_health_aggregate_status_is_valid():
    client = _client()
    body = client.get("/health").json()
    assert body["status"] in ("ok", "degraded")
