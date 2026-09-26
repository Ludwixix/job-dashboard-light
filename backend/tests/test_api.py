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


def test_spa_fallback_dev_mode():
    """Verify that SPA fallback returns 200 JSON message in dev mode."""
    response = client.get("/dashboard")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "running"
