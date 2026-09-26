"""
Unit tests for FastAPI entrypoint and health probe.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from job_dashboard_light.main import app

client = TestClient(app)


def test_health_check_endpoint():
    """Verify that /health returns healthy status and service identification."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "job-dashboard-light"
    assert "storage" in data


def test_spa_fallback():
    """Verify that SPA fallback returns 200 (HTML in production/built static or JSON fallback in bare dev)."""
    response = client.get("/dashboard")
    assert response.status_code == 200
    if response.headers.get("content-type", "").startswith("text/html"):
        assert "<div id=\"root\"></div>" in response.text or "<!DOCTYPE html>" in response.text
    else:
        data = response.json()
        assert data["status"] == "running"
