"""Optional bearer/API and browser-session authentication for the web backend."""

import secrets
import time
from urllib.parse import urlsplit

import jwt
from fastapi import FastAPI, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse

SESSION_COOKIE = "janito_web_session"
SESSION_MAX_AGE = 12 * 60 * 60


def add_cors(app: FastAPI) -> None:
    """Allow development API clients, without cross-origin cookie access."""
    app.add_middleware(
        CORSMiddleware, allow_origins=["*"], allow_credentials=False,
        allow_methods=["*"], allow_headers=["*"],
    )


def same_origin(connection: Request | WebSocket) -> bool:
    """Reject browser requests from another origin, including opaque origins."""
    origin = connection.headers.get("origin")
    if origin is None:
        return True  # Non-browser clients need not send Origin.
    expected_scheme = {"ws": "http", "wss": "https"}.get(connection.url.scheme, connection.url.scheme)
    try:
        actual = urlsplit(origin)
        expected = urlsplit(f"{expected_scheme}://{connection.url.netloc}")
        actual_port = actual.port if actual.port is not None else (443 if actual.scheme == "https" else 80)
        expected_port = expected.port if expected.port is not None else (443 if expected.scheme == "https" else 80)
        return (
            actual.scheme == expected.scheme
            and actual.hostname == expected.hostname
            and actual_port == expected_port
            and actual.username is None and actual.password is None
            and not actual.path and not actual.query and not actual.fragment
        )
    except ValueError:
        return False


class WebAuthenticator:
    """Own token validation and short-lived, process-local browser sessions."""

    def __init__(self, auth_token: str | None):
        self.auth_token = auth_token
        self._session_key = secrets.token_bytes(32)

    @property
    def enabled(self) -> bool:
        return self.auth_token is not None

    def valid_token(self, token: object) -> bool:
        if not isinstance(token, str) or not 0 < len(token) <= 4096 or self.auth_token is None:
            return False
        return secrets.compare_digest(
            token.encode("utf-8", errors="surrogatepass"), self.auth_token.encode("utf-8", errors="surrogatepass")
        )

    def bearer_authorized(self, connection: Request | WebSocket) -> bool:
        header = connection.headers.get("authorization", "")
        scheme, _, token = header.partition(" ")
        return scheme.lower() == "bearer" and self.valid_token(token)

    def issue_session(self) -> str:
        return jwt.encode(
            {"exp": int(time.time()) + SESSION_MAX_AGE, "aud": "janito-web"},
            self._session_key, algorithm="HS256",
        )

    def session_authorized(self, connection: Request | WebSocket) -> bool:
        cookie = connection.cookies.get(SESSION_COOKIE)
        if not cookie:
            return False
        try:
            jwt.decode(
                cookie, self._session_key, algorithms=["HS256"], audience="janito-web",
                options={"require": ["exp", "aud"]},
            )
        except jwt.InvalidTokenError:
            return False
        return True


class TokenAuthMiddleware:
    """Protect the UI and API; browser credentials never enter page scripts."""

    def __init__(self, app, authenticator: WebAuthenticator):
        self.app = app
        self.authenticator = authenticator

    async def __call__(self, scope, receive, send):
        if not self.authenticator.enabled or scope["type"] not in {"http", "websocket"}:
            await self.app(scope, receive, send)
            return
        if scope["type"] == "websocket":
            await self._websocket(scope, receive, send)
            return
        request = Request(scope, receive)
        path = request.url.path
        # Assets are public and contain no credentials; protect the page/API/docs.
        protected = path == "/" or path.startswith(("/api", "/docs", "/redoc", "/openapi.json"))
        if not protected or self.authenticator.bearer_authorized(request):
            await self.app(scope, receive, send)
            return
        if self.authenticator.session_authorized(request):
            if request.method in {"GET", "HEAD", "OPTIONS"} or same_origin(request):
                await self.app(scope, receive, send)
                return
            response = JSONResponse({"detail": "Cross-origin request denied"}, status_code=403)
        elif path == "/":
            response = RedirectResponse("/login", status_code=303)
        else:
            response = JSONResponse({"detail": "Unauthorized"}, status_code=401)
        response.headers["Cache-Control"] = "no-store"
        await response(scope, receive, send)

    async def _websocket(self, scope, receive, send):
        connection = WebSocket(scope, receive, send)
        authorized = self.authenticator.bearer_authorized(connection) or (
            self.authenticator.session_authorized(connection) and same_origin(connection)
        )
        if authorized:
            await self.app(scope, receive, send)
        else:
            await send({"type": "websocket.close", "code": 1008})
