"""Auth & admin API (P5-01 multi-tenant foundation): sessions in a HttpOnly
cookie, register/login/logout/me, admin user management + credits + host flags.

Local single-owner mode: hosted_mode is OFF by default (config/ui_settings.yaml
keys hosted_mode / registration_open) — then nothing here is required and the
whole app works exactly as before.
"""

import json
import os
import time
from collections import defaultdict, deque

import yaml
from fastapi import Request
from starlette.responses import JSONResponse

import ui.server as srv
from core import tenants
from ui.server import app

COOKIE = "ui_session"


def _secure_cookie() -> bool:
    """Secure cookie flag: env override, or the host flag in ui_settings.yaml."""
    if os.environ.get("UI_HTTPS", "") == "1":
        return True
    try:
        return bool(tenants.read_flags(srv.WORKSPACE).get("https"))
    except Exception:  # noqa: BLE001
        return False


# naive per-IP rate limit for auth endpoints (hosted: no brute force)
_AUTH_ATTEMPTS: dict = defaultdict(lambda: deque(maxlen=10))
AUTH_WINDOW = 60.0
AUTH_MAX = 8


def _rate_limited(ip: str) -> bool:
    now = time.time()
    dq = _AUTH_ATTEMPTS[ip]
    while dq and now - dq[0] > AUTH_WINDOW:
        dq.popleft()
    return len(dq) >= AUTH_MAX


def _set_cookie(resp, token: str):
    resp.set_cookie(COOKIE, token, max_age=tenants.SESSION_TTL,
                    httponly=True, samesite="lax", secure=_secure_cookie(), path="/")
    return resp


async def _json_body(request: Request) -> dict:
    try:
        body = json.loads((await request.body()).decode("utf-8") or "{}")
        return body if isinstance(body, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


@app.get("/api/auth/me")
def api_auth_me(request: Request):
    user = getattr(request.state, "tenant_user", None)
    return {"hosted_mode": tenants.hosted_mode(srv.WORKSPACE),
            "registration_open": tenants.registration_open(srv.WORKSPACE),
            "user": user}


@app.get("/api/auth/legal")
def api_auth_legal(name: str = "terms"):
    """Terms/privacy text for the registration gate. Host-level documents in
    notes/legal/<name>.md (copy the *_template.md and fill it in)."""
    if name not in ("terms", "privacy"):
        return JSONResponse({"error": "bad name"}, status_code=400)
    f = srv.WORKSPACE / "notes" / "legal" / f"{name}.md"
    if not f.exists():
        return {"text": "", "missing": True}
    return {"text": f.read_text(encoding="utf-8")}


@app.post("/api/auth/register")
async def api_auth_register(request: Request):
    ip = (request.client.host if request.client else "?")
    if _rate_limited(ip):
        return JSONResponse({"error": "too many attempts, try later"}, status_code=429)
    _AUTH_ATTEMPTS[ip].append(time.time())
    body = await _json_body(request)
    if not tenants.registration_open(srv.WORKSPACE) and tenants.user_count(srv.WORKSPACE) > 0:
        return JSONResponse({"error": "registration is closed"}, status_code=403)
    if tenants.hosted_mode(srv.WORKSPACE) and not body.get("accepted_terms"):
        return JSONResponse({"error": "you must accept the terms"}, status_code=400)
    try:
        user = tenants.register_user(srv.WORKSPACE, str(body.get("email") or ""), str(body.get("password") or ""))
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    token = tenants.create_session(srv.WORKSPACE, user["id"])
    return _set_cookie(JSONResponse({"ok": True, "user": user}), token)


@app.post("/api/auth/login")
async def api_auth_login(request: Request):
    ip = (request.client.host if request.client else "?")
    if _rate_limited(ip):
        return JSONResponse({"error": "too many attempts, try later"}, status_code=429)
    _AUTH_ATTEMPTS[ip].append(time.time())
    body = await _json_body(request)
    user = tenants.authenticate(srv.WORKSPACE, str(body.get("email") or ""), str(body.get("password") or ""))
    if not user:
        return JSONResponse({"error": "wrong email or password"}, status_code=401)
    token = tenants.create_session(srv.WORKSPACE, user["id"])
    return _set_cookie(JSONResponse({"ok": True, "user": user}), token)


@app.post("/api/auth/logout")
async def api_auth_logout(request: Request):
    tok = request.cookies.get(COOKIE) or ""
    if request.headers.get("authorization", "").startswith("Bearer "):
        tok = request.headers["authorization"][7:]
    if tok:
        tenants.delete_session(srv.WORKSPACE, tok)
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(COOKIE, path="/")
    return resp


def _require_admin(request: Request) -> dict | None:
    user = getattr(request.state, "tenant_user", None)
    if not user or user.get("role") != "admin":
        return None
    return user


@app.get("/api/admin/users")
def api_admin_users(request: Request):
    if not _require_admin(request):
        return JSONResponse({"error": "admin only"}, status_code=403)
    return {"users": tenants.list_users(srv.WORKSPACE)}


@app.post("/api/admin/credits")
async def api_admin_credits(request: Request):
    if not _require_admin(request):
        return JSONResponse({"error": "admin only"}, status_code=403)
    body = await _json_body(request)
    try:
        amount = float(body.get("amount", 0))
    except (TypeError, ValueError):
        return JSONResponse({"error": "bad amount"}, status_code=400)
    user = tenants.add_credits(srv.WORKSPACE, str(body.get("uid") or ""), amount)
    if not user:
        return JSONResponse({"error": "нет такого пользователя"}, status_code=404)
    return {"ok": True, "user": user}


@app.post("/api/admin/set_flag")
async def api_admin_set_flag(request: Request):
    if not _require_admin(request):
        return JSONResponse({"error": "admin only"}, status_code=403)
    body = await _json_body(request)
    field = body.get("field")
    if field not in ("disabled", "unlimited"):
        return JSONResponse({"error": "bad field"}, status_code=400)
    user = tenants.set_user_flag(srv.WORKSPACE, str(body.get("uid") or ""), field, body.get("value"))
    if not user:
        return JSONResponse({"error": "нет такого пользователя"}, status_code=404)
    return {"ok": True, "user": user}


@app.post("/api/admin/host_flags")
async def api_admin_host_flags(request: Request):
    if not _require_admin(request):
        return JSONResponse({"error": "admin only"}, status_code=403)
    body = await _json_body(request)
    path = srv.WORKSPACE / "config" / "ui_settings.yaml"
    data = {}
    if path.exists():
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    for k in ("hosted_mode", "registration_open"):
        if k in body:
            data[k] = bool(body[k])
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return {"ok": True, "flags": tenants.read_flags(srv.WORKSPACE)}
