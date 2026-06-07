"""
Day 1 — FastAPI health endpoint test.
No API keys needed. No server needed (uses TestClient).

Run:
    python tests/test_health.py
    pytest tests/test_health.py -v
"""
import sys
import os

# Stub env vars so pydantic Settings() doesn't fail on missing keys
for k in ["ANTHROPIC_API_KEY", "DEEPGRAM_API_KEY", "ELEVENLABS_API_KEY"]:
    os.environ.setdefault(k, "stub")
os.environ.setdefault("ELEVENLABS_VOICE_ID", "stub")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_health_status_code():
    r = client.get("/health")
    assert r.status_code == 200, f"Expected 200, got {r.status_code}"


def test_health_body():
    r = client.get("/health")
    assert r.json() == {"status": "ok"}, f"Unexpected body: {r.json()}"


def test_unknown_route_404():
    r = client.get("/nonexistent")
    assert r.status_code == 404


def test_health_content_type():
    r = client.get("/health")
    assert "application/json" in r.headers["content-type"]


if __name__ == "__main__":
    test_health_status_code()
    print("[OK] GET /health -> 200")
    test_health_body()
    print('[OK] body {"status": "ok"}')
    test_unknown_route_404()
    print("[OK] unknown route -> 404")
    test_health_content_type()
    print("[OK] content-type: application/json")
    print("\nAll health checks passed.")
