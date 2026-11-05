"""Explicit browser login: exchange the shared token for an HttpOnly cookie."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from ..security import SESSION_COOKIE, SESSION_MAX_AGE, same_origin
from ..templating import make_environment

router = APIRouter()


@router.get("/login", response_class=HTMLResponse, include_in_schema=False)
async def login_page(request: Request):
    authenticator = request.app.state.web_auth
    if not authenticator.enabled or authenticator.session_authorized(request):
        return RedirectResponse("/", status_code=303)
    html = make_environment().get_template("login.html").render()
    return HTMLResponse(html, headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})


@router.post("/auth/login", include_in_schema=False)
async def login(request: Request):
    authenticator = request.app.state.web_auth
    if not same_origin(request):
        return JSONResponse({"detail": "Cross-origin request denied"}, status_code=403)
    try:
        body = await request.json()
    except (ValueError, UnicodeError):
        return JSONResponse({"detail": "Invalid request"}, status_code=400, headers={"Cache-Control": "no-store"})
    token = body.get("token") if isinstance(body, dict) else None
    # Do not echo credential input through framework validation errors.
    if not authenticator.enabled or not authenticator.valid_token(token):
        return JSONResponse({"detail": "Unauthorized"}, status_code=401, headers={"Cache-Control": "no-store"})
    response = JSONResponse({"authenticated": True}, headers={"Cache-Control": "no-store"})
    response.set_cookie(
        SESSION_COOKIE, authenticator.issue_session(), max_age=SESSION_MAX_AGE,
        httponly=True, secure=request.url.scheme == "https", samesite="strict", path="/",
    )
    return response


@router.post("/auth/logout", include_in_schema=False)
async def logout(request: Request):
    if not same_origin(request):
        return JSONResponse({"detail": "Cross-origin request denied"}, status_code=403)
    response = JSONResponse({"authenticated": False}, headers={"Cache-Control": "no-store"})
    response.delete_cookie(SESSION_COOKIE, path="/", httponly=True, samesite="strict")
    return response
