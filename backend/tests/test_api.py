"""
Smoke tests for the FastAPI app.
Uses TestClient — no real database connection required.
The DB call in main.py (create_all) is patched out.
"""

from unittest.mock import patch


# Patch create_all before the app module is imported so it doesn't try
# to connect to a real database during test collection.
with patch("sqlalchemy.engine.base.Engine.connect"):
    with patch("sqlalchemy.schema.MetaData.create_all"):
        from fastapi.testclient import TestClient
        from app.main import app

client = TestClient(app)


def test_health_returns_ok():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_docs_endpoint_reachable():
    response = client.get("/api/docs")
    assert response.status_code == 200


def test_unknown_route_returns_404():
    response = client.get("/does-not-exist")
    assert response.status_code == 404
