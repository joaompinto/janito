"""Contract tests for the web health endpoint (``GET /health``).

The health check is intentionally outside ``/api`` because
``TokenAuthMiddleware`` protects everything under ``/api``. Container
orchestrators and the Docker ``HEALTHCHECK`` must be able to probe it
without a bearer token even when ``JANITO_WEB_TOKEN`` is set.

These tests pin down:

1. ``GET /health`` returns 200 and the configured model;
2. it stays reachable without ``Authorization`` when token auth is enabled;
3. the old protected ``/api/health`` path is gone;
4. other ``/api`` routes still require the token.
"""

import sys
from pathlib import Path

# Add the repo root to sys.path to allow importing the package directly.
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pytest

# The web routes need the optional `web` extra (fastapi). Skip gracefully
# when fastapi is not installed (e.g. minimal tox envs).
try:
    import fastapi  # noqa: F401
    from fastapi.testclient import TestClient

    _HAS_FASTAPI = True
except ModuleNotFoundError:
    _HAS_FASTAPI = False

requires_fastapi = pytest.mark.skipif(not _HAS_FASTAPI, reason="fastapi (web extra) is not installed")


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """A TestClient with bearer-token auth enabled."""
    import janito.config_loaders as config_loaders_mod
    from janito.web.backend.app import create_app
    from janito.web.backend.config import WebServerConfig

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(config_loaders_mod, "load_system_prompt_start", lambda: (None, None))

    config = WebServerConfig(
        web_host="127.0.0.1",
        web_port=0,
        no_web_open=True,
        auth_token="secret-token",
    )
    app = create_app(config)
    with TestClient(app) as c:
        yield c


@requires_fastapi
def test_health_is_public(client):
    """GET /health works without a token and reports the model."""
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
    assert "model" in resp.json()


@requires_fastapi
def test_health_ignores_bearer_token_when_supplied(client):
    """A supplied token is accepted too (the route is simply unprotected)."""
    resp = client.get("/health", headers={"Authorization": "Bearer secret-token"})
    assert resp.status_code == 200


@requires_fastapi
def test_old_api_health_path_is_gone(client):
    """/api/health no longer exists, so it can't collide with auth rules."""
    resp = client.get("/api/health", headers={"Authorization": "Bearer secret-token"})
    assert resp.status_code == 404


@requires_fastapi
def test_api_routes_still_require_token(client):
    """Moving /health must not weaken auth on the rest of /api."""
    assert client.get("/api/config").status_code == 401
    assert client.get("/api/config", headers={"Authorization": "Bearer secret-token"}).status_code == 200
