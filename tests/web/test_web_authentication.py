"""Browser login, API auth, expiry and cross-origin protections."""

import json
import time
from urllib.parse import urlencode

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from janito.config_dir import set_config_dir
from janito.web.backend.app import create_app
from janito.web.backend.config import WebServerConfig
from janito.web.backend.security import SESSION_COOKIE, SESSION_MAX_AGE

TOKEN = 'test-token-with-"<&>+-unicode-é'


@pytest.fixture()
def app(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    set_config_dir(str(tmp_path / "config"))
    return create_app(WebServerConfig(auth_token=TOKEN, no_history=True))


@pytest.fixture()
def client(app):
    with TestClient(app) as connection:
        yield connection


def sign_in(client):
    response = client.post("/auth/login", json={"token": TOKEN}, headers={"Origin": str(client.base_url).rstrip("/")})
    assert response.status_code == 200
    return response


@pytest.mark.parametrize("path", ["/api/health", "/api/config", "/docs", "/redoc", "/openapi.json"])
def test_api_and_docs_require_authentication(client, path):
    assert client.get(path).status_code == 401


def test_page_requires_explicit_login_and_never_reveals_token(client):
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"
    page = client.get("/login")
    assert page.status_code == 200
    assert page.headers["cache-control"] == "no-store"
    assert TOKEN not in page.text
    assert client.get("/js/login.js").status_code == 200
    assert client.get("/css/theme.css").status_code == 200


@pytest.mark.parametrize("body", [
    {"token": "wrong"}, {"token": ""}, {"token": 123}, {}, {"token": "x" * 4097}, {"token": "\ud800"},
    None, [], 123,
])
def test_invalid_login_does_not_issue_credentials(client, body):
    response = client.post("/auth/login", content=json.dumps(body), headers={"Content-Type": "application/json"})
    assert response.status_code == 401
    assert SESSION_COOKIE not in client.cookies
    assert client.get("/api/health").status_code == 401


def test_malformed_login_body_is_rejected(client):
    response = client.post("/auth/login", content="{", headers={"Content-Type": "application/json"})
    assert response.status_code == 400
    assert SESSION_COOKIE not in client.cookies


def test_login_issues_httponly_cookie_without_shared_secret(client):
    response = sign_in(client)
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie
    assert "samesite=strict" in cookie
    assert f"max-age={SESSION_MAX_AGE}" in cookie
    assert TOKEN not in response.text
    assert TOKEN not in client.cookies[SESSION_COOKIE]
    assert client.get("/api/health").status_code == 200
    assert client.get("/").status_code == 200
    assert "__JANITO_TOKEN__" not in client.get("/").text


def test_https_cookie_is_secure(app):
    with TestClient(app, base_url="https://testserver") as client:
        assert "secure" in sign_in(client).headers["set-cookie"].lower()
        assert client.get("/api/health").status_code == 200


def test_logout_clears_browser_credentials(client):
    sign_in(client)
    assert client.post("/auth/logout", headers={"Origin": "http://testserver"}).status_code == 200
    assert SESSION_COOKIE not in client.cookies
    assert client.get("/api/health").status_code == 401


def test_bearer_header_still_authenticates_api_clients(client):
    assert client.get("/api/health", headers={"Authorization": "Bearer wrong"}).status_code == 401
    # HTTP headers are Latin-1; exercise Unicode tokens through JSON login instead.
    client.app.state.web_auth.auth_token = "ascii-api-token"
    assert client.get("/api/health", headers={"Authorization": "Bearer ascii-api-token"}).status_code == 200


def test_query_tokens_are_not_credentials(client):
    assert client.get("/api/health", params={"token": TOKEN}).status_code == 401
    with pytest.raises(WebSocketDisconnect) as closed:
        with client.websocket_connect("/api/chat/ws/unknown?" + urlencode({"token": TOKEN})):
            pass
    assert closed.value.code == 1008


def test_bearer_header_can_authenticate_websocket_clients(client):
    client.app.state.web_auth.auth_token = "ascii-api-token"
    session_id = client.app.state.sessions.create().session_id
    with client.websocket_connect(
        f"/api/chat/ws/{session_id}", headers={"Authorization": "Bearer ascii-api-token"},
    ) as websocket:
        assert websocket.receive_json()["type"] == "session_start"


@pytest.mark.parametrize("origin", [
    "http://evil.example", "https://testserver", "null", "http://testserver.evil",
    "http://testserver:0", "http://@testserver", "http://testserver/path", "http://testserver:invalid",
])
def test_cross_origin_login_and_logout_are_rejected(client, origin):
    assert client.post("/auth/login", json={"token": TOKEN}, headers={"Origin": origin}).status_code == 403
    sign_in(client)
    assert client.post("/auth/logout", headers={"Origin": origin}).status_code == 403
    assert client.get("/api/health").status_code == 200


@pytest.mark.parametrize("origin", ["http://evil.example", "https://testserver", "null"])
def test_cookie_authenticated_writes_reject_foreign_origins(client, origin):
    sign_in(client)
    assert client.post("/api/chat/sessions", headers={"Origin": origin}).status_code == 403
    assert client.app.state.sessions.list_sessions() == []


def test_same_origin_cookie_write_and_websocket(client):
    sign_in(client)
    response = client.post("/api/chat/sessions", headers={"Origin": "http://testserver"})
    assert response.status_code == 200
    session_id = response.json()["session_id"]
    with client.websocket_connect(f"/api/chat/ws/{session_id}", headers={"Origin": "http://testserver"}) as websocket:
        assert websocket.receive_json()["type"] == "session_start"


@pytest.mark.parametrize("logged_in, origin", [(False, "http://testserver"), (True, "http://evil.example")])
def test_unauthorized_or_cross_origin_websocket_is_rejected(client, logged_in, origin):
    if logged_in:
        sign_in(client)
    with pytest.raises(WebSocketDisconnect) as closed:
        with client.websocket_connect("/api/chat/ws/unknown", headers={"Origin": origin}):
            pass
    assert closed.value.code == 1008


def test_invalid_session_cookie_is_rejected(client):
    client.cookies.set(SESSION_COOKIE, "forged")
    assert client.get("/api/health").status_code == 401


def test_expired_session_is_rejected(client, monkeypatch):
    now = time.time()
    with monkeypatch.context() as patch:
        patch.setattr(time, "time", lambda: now - SESSION_MAX_AGE - 60)
        expired = client.app.state.web_auth.issue_session()
    client.cookies.set(SESSION_COOKIE, expired)
    assert client.get("/api/health").status_code == 401


def test_server_restart_invalidates_cookie(client):
    sign_in(client)
    restarted = create_app(WebServerConfig(auth_token=TOKEN, no_history=True))
    with TestClient(restarted) as fresh:
        fresh.cookies.set(SESSION_COOKIE, client.cookies[SESSION_COOKIE])
        assert fresh.get("/api/health").status_code == 401


def test_auth_disabled_keeps_local_ui_and_api_usable(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with TestClient(create_app(WebServerConfig(no_history=True))) as client:
        assert client.get("/").status_code == 200
        assert client.get("/api/health").status_code == 200
        assert client.get("/login", follow_redirects=False).status_code == 303
