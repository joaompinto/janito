"""FastAPI application factory + ``run_web(args)`` entry point.

At the point ``run_web`` is called, ``__main__.py`` has already:
  - configured logging
  - set ``running_privileges`` from -r -w -x
  - validated the runtime config (API key / endpoint / model)
"""

import logging
import re
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from .config import WebServerConfig
from .security import TokenAuthMiddleware, WebAuthenticator, add_cors
from .session import SessionManager
from .templating import make_environment

logger = logging.getLogger(__name__)


def _cache_bust_assets(html: str, frontend_dir: Path) -> str:
    """Append an mtime-based query string to local ``/js/`` and ``/css/``
    asset URLs so browsers fetch a new copy whenever the file changes.

    Only same-origin paths starting with ``/js/`` or ``/css/`` are touched —
    CDN scripts/styles and the inline theme bootstrap are left alone.
    """

    def _stamp(match: re.Match) -> str:
        attr, path = match.group(1), match.group(2)
        rel = path.lstrip("/")
        target = frontend_dir / rel
        try:
            mtime = int(target.stat().st_mtime)
        except OSError:
            return match.group(0)  # file missing — leave the URL untouched
        return f'{attr}="{path}?v={mtime}"'

    # Match src="/js/..." or href="/css/..." (no existing query string).
    return re.sub(
        r'(src|href)="(/(?:js|css)/[^"?]+)"',
        _stamp,
        html,
    )


def create_app(config: WebServerConfig) -> FastAPI:
    """Build the FastAPI application."""
    # Building the web app declares the web UI as a question-answering
    # surface: the AskUser tool's should_load() gate loads it even when
    # stdin is not an interactive terminal (headless/service deployments),
    # because questions are answered through the in-browser question cards.
    # Must precede any tool discovery triggered below (the routers read the
    # tools registry).
    from janito.tooling.prompting import enable_browser_prompts

    enable_browser_prompts()

    from .routers import auth as auth_router
    from .routers import chat as chat_router
    from .routers import config as config_router
    from .routers import images as images_router
    from .routers import mcp as mcp_router
    from .routers import tools as tools_router

    app = FastAPI(title="Janito Web", version="0.1.0")

    # Store config + session manager on app state
    app.state.config = config
    app.state.web_auth = WebAuthenticator(config.auth_token)
    app.state.sessions = SessionManager(config)
    # Restore conversations persisted to .janito/sessions/ (issue #36) so
    # they survive a server restart. No-op with --no-history.
    app.state.sessions.load_from_disk()

    # Enable toolsets from CLI flags
    config.apply_toolsets()

    # Optional bearer-token auth (no-op when auth_token is None)
    app.add_middleware(TokenAuthMiddleware, authenticator=app.state.web_auth)

    # CORS for development
    add_cors(app)

    # API routers
    app.include_router(auth_router.router)
    app.include_router(chat_router.router, prefix="/api/chat", tags=["chat"])
    app.include_router(config_router.router, prefix="/api/config", tags=["config"])
    app.include_router(tools_router.router, prefix="/api/tools", tags=["tools"])
    app.include_router(mcp_router.router, prefix="/api/mcp", tags=["mcp"])
    app.include_router(images_router.router, prefix="/api/images", tags=["images"])

    @app.get("/api/health")
    async def health():
        return {"status": "ok", "model": config.model}

    # Serve frontend (no build step — plain HTML/JS/CSS)
    frontend_dir = Path(__file__).parent.parent / "frontend"
    if frontend_dir.exists():
        # Authentication is handled by the middleware and an HttpOnly cookie;
        # no credentials are passed into templates or browser scripts.
        template_env = make_environment()

        @app.get("/", response_class=HTMLResponse, include_in_schema=False)
        async def serve_index():
            # Render per request so frontend edits apply without restarting
            # the server (Jinja2's FileSystemLoader auto-reloads on mtime
            # changes), and send ``no-store`` so browsers never serve a
            # stale shell.
            html = template_env.get_template("base.html").render(auth_enabled=app.state.web_auth.enabled)
            # Cache-bust local /js/ + /css/ assets by fingerprinting each
            # reference with its file mtime. Browsers aggressively cache
            # these scripts, so without this a frontend edit (e.g. a new
            # Alpine method in settings.js) keeps serving the stale copy
            # and raises "X is not defined" against the fresh page.
            html = _cache_bust_assets(html, frontend_dir)
            return HTMLResponse(html, headers={"Cache-Control": "no-store"})

        # Mount everything else (css/, js/, favicon, etc.) as static files.
        # html=False so "/" is handled by our dynamic route above.
        app.mount("/", StaticFiles(directory=str(frontend_dir), html=False))
    else:
        logger.warning(f"Frontend directory not found: {frontend_dir}")

    return app


def _ensure_web_logging(args) -> None:
    """Make web-backend diagnostic logs visible.

    The default CLI logging setup (``setup_logging`` with no ``--log``) leaves
    the root logger without handlers and above CRITICAL, which silently drops
    the ``logger.warning`` diagnostics added for the WebSocket/auth path.
    When no explicit ``--log`` is given, install a stderr handler at WARNING so
    those messages show up while debugging connection issues.
    """
    if getattr(args, "log", None):
        return  # user configured logging explicitly; leave it alone
    root = logging.getLogger()
    if not root.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(levelname)s: %(name)s: %(message)s"))
        root.addHandler(handler)
        root.setLevel(logging.WARNING)


def run_web(args) -> None:
    """Entry point called from ``__main__.py`` when ``--web`` is passed."""
    import uvicorn

    # Ensure web-backend diagnostic logs (auth/WS handshake) are visible even
    # without --log: the default CLI logging config installs no handlers.
    _ensure_web_logging(args)

    config = WebServerConfig.from_args(args)
    app = create_app(config)

    url = f"http://{config.web_host}:{config.web_port}"

    if not config.no_web_open:
        import threading
        import webbrowser

        def _open():
            try:
                webbrowser.open(url)
            except Exception as e:  # noqa: BLE001 - intentional boundary, log/convert and continue
                logger.debug(f"Could not open browser: {e}")

        # Open the browser slightly after the server starts listening
        threading.Timer(0.8, _open).start()

    # Banner (mirrors CLI aesthetics, plain print — no Rich dependency here)
    print(f"Janito Web UI running at {url}")
    print(f"  Model: {config.model or '?'}")
    if config.auth_token:
        print("  Auth: bearer token required (JANITO_WEB_TOKEN is set)")
    print("  Press Ctrl+C to stop.")

    try:
        uvicorn.run(app, host=config.web_host, port=config.web_port, log_level="warning")
    finally:
        from janito.mcp_manager import shutdown_mcp_manager

        try:
            shutdown_mcp_manager()
        except Exception:  # noqa: BLE001 - intentional boundary, log/convert and continue
            pass
