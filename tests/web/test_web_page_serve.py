"""Contract tests for serving the web chat page (``GET /``).

The page shell (``janito/web/backend/templates/base.html`` + partials) is
composed server-side with Jinja2.  These tests pin down the serving contract:

1. ``GET /`` returns ``200`` with ``Cache-Control: no-store`` and the fully
   composed page (all major UI sections present);
2. the bearer token is never injected into page HTML;
3. local ``/js/`` + ``/css/`` assets are cache-busted with an mtime query
   string while CDN scripts/styles are left untouched.
"""

import re
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

LOCAL_ASSET = re.compile(r'(?:src|href)="(/(?:js|css)/[^"]+)"')


@pytest.fixture()
def client():
    """A TestClient wired to a fresh Janito web app."""
    from janito.web.backend.app import create_app
    from janito.web.backend.config import WebServerConfig

    config = WebServerConfig(web_host="127.0.0.1", web_port=0, no_web_open=True)
    app = create_app(config)
    with TestClient(app) as c:
        yield c


@requires_fastapi
def test_index_serves_composed_page(client):
    """GET / returns the fully composed page with no-store caching."""
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.headers["cache-control"] == "no-store"
    html = resp.text
    # The page shell + the partials that make up the UI.
    for marker in (
        'x-data="appComponent()"',
        'x-data="chatComponent()"',
        "providerSwitcherComponent()",
        "statusBarComponent()",
        "settingsComponent()",
        "mcpComponent()",
        'class="session-start-banner"',
        "part.kind === 'tool'",
        "toolsDialogOpen",
        "keyModalOpen",
        "mcpOpen",
        'class="toast"',
    ):
        assert marker in html


@requires_fastapi
def test_index_never_injects_auth_token(tmp_path, monkeypatch):
    """Only an authenticated browser sees the page, without shared credentials."""
    from janito.web.backend.app import create_app
    from janito.web.backend.config import WebServerConfig

    monkeypatch.chdir(tmp_path)
    token = 'tok"en<>&'
    config = WebServerConfig(web_host="127.0.0.1", web_port=0, no_web_open=True, auth_token=token, no_history=True)
    app = create_app(config)
    with TestClient(app) as c:
        assert c.get("/", follow_redirects=False).status_code == 303
        assert c.post("/auth/login", json={"token": token}).status_code == 200
        html = c.get("/").text
    assert token not in html
    assert "__JANITO_TOKEN__" not in html


@requires_fastapi
def test_index_cache_busts_local_assets_only(client):
    """/js/ and /css/ get an mtime query string; CDN assets are untouched."""
    html = client.get("/").text
    local = LOCAL_ASSET.findall(html)
    assert local, "no local /js/ or /css/ assets found"
    assert all("?v=" in url for url in local)
    # CDN-hosted scripts/styles are left alone (no query string).
    cdn_markers = [
        "https://cdn.jsdelivr.net/npm/marked/marked.min.js",
        "https://cdn.jsdelivr.net/gh/highlightjs/cdn-release/build/highlight.min.js",
        "https://cdn.jsdelivr.net/npm/dompurify@3/dist/purify.min.js",
        "https://cdn.jsdelivr.net/npm/alpinejs@3/dist/cdn.min.js",
        "https://cdn.jsdelivr.net/gh/highlightjs/cdn-release/build/styles/tokyo-night-dark.min.css",
    ]
    for url in cdn_markers:
        assert url in html and url + "?v=" not in html
