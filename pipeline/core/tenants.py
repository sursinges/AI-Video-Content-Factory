"""Multi-tenant foundation (stage 2 / P5): local accounts, sessions, per-tenant
data roots, credits. Local single-owner mode is untouched: with no tenant in
context everything resolves to the global workspace (architecture §8, decision
2026-09-27 — host-version first).

Isolation model (v1):
  - DATA (runs/, data/state.db, data/library.db, notes/, transcripts/) is
    per-tenant: workspace/data/tenants/<uid>/...
  - CONFIG (providers.yaml, profiles, formats, presets) and machine assets
    (models/, prompts/) stay global — the host runs engines with its own keys
    and bills credits per episode. Per-tenant BYOK is a later step.
  - Resolution: UI process uses the contextvar (set by middleware);
    pipeline subprocesses receive PIPELINE_DATA_ROOT (full tenant data dir).
"""

import contextvars
import hashlib
import json
import os
import secrets
import sqlite3
import time
from pathlib import Path

_TENANT: contextvars.ContextVar[str] = contextvars.ContextVar("pipeline_tenant", default="")
SESSION_TTL = 30 * 24 * 3600  # 30 days
_PBKDF2_ITERS = 200_000

USERS_DB = "users.db"


def set_tenant(uid: str):
    return _TENANT.set(uid)


def reset_tenant(tok):
    _TENANT.reset(tok)


def current_tenant() -> str:
    return _TENANT.get()


def tenant_dir(workspace: str | Path, uid: str | None = None) -> Path:
    """Per-tenant data dir: workspace/data/tenants/<uid>/ (dirs created)."""
    uid = uid or current_tenant()
    if not uid:
        raise ValueError("no tenant in context")
    root = Path(workspace) / "data" / "tenants" / uid
    for sub in ("", "config", "data", "runs", "notes", "transcripts"):
        (root / sub).mkdir(parents=True, exist_ok=True)
    return root


def config_root(workspace: str | Path) -> Path:
    """Per-tenant config dir (providers.yaml / profile / formats / presets /
    visual presets) — the tenant BYOK layer. Global config stays for owners."""
    if current_tenant():
        return tenant_dir(workspace) / "config"
    return Path(workspace) / "config"


def resolve_config(workspace: str | Path, rel: str) -> Path:
    """Read-through: tenant override file if present, else the global one."""
    rel = rel.replace("\\", "/").lstrip("/")
    if current_tenant():
        p = tenant_dir(workspace) / rel
        if p.exists():
            return p
    return Path(workspace) / rel


def secrets_env(workspace: str | Path) -> Path:
    """Where provider API keys are stored for the current context:
    tenant .env for tenants, the global .env for the owner."""
    if current_tenant():
        return tenant_dir(workspace) / ".env"
    return Path(workspace) / ".env"


def load_env_stacked(workspace: str | Path) -> None:
    """Global .env first, tenant .env overrides — for in-process provider calls
    (UI endpoints). Pipeline subprocesses get the same via PIPELINE_DATA_ROOT
    inside Orchestrator.__init__."""
    from core.secrets import load_env

    load_env(Path(workspace) / ".env")
    if current_tenant():
        load_env(tenant_dir(workspace) / ".env")


def refund_credit(workspace: str | Path, uid: str) -> None:
    """Return 1 credit to a regular user (failed run). Admins/unlimited never
    spent one."""
    conn = _connect(workspace)
    try:
        conn.execute(
            "UPDATE users SET credits = credits + 1 "
            "WHERE id=? AND role != 'admin' AND unlimited = 0", (uid,))
        conn.commit()
    finally:
        conn.close()


def resolve_data_root(workspace: str | Path) -> Path:
    """Data root for the current context: tenant dir, or env override (set for
    pipeline subprocesses), or the global workspace itself."""
    ws = Path(workspace)
    if current_tenant():
        return tenant_dir(ws)
    env = os.environ.get("PIPELINE_DATA_ROOT", "")
    if env:
        p = Path(env)
        for sub in ("", "data", "runs", "notes", "transcripts"):
            (p / sub).mkdir(parents=True, exist_ok=True)
        return p
    return ws


# ---------- flags (config/ui_settings.yaml) ----------

def _ui_settings_path(workspace: str | Path) -> Path:
    return Path(workspace) / "config" / "ui_settings.yaml"


def read_flags(workspace: str | Path) -> dict:
    try:
        import yaml

        data = yaml.safe_load(_ui_settings_path(workspace).read_text(encoding="utf-8")) or {}
    except Exception:  # noqa: BLE001 — missing/broken file = local mode
        return {}
    return {"hosted_mode": bool(data.get("hosted_mode", False)),
            "registration_open": bool(data.get("registration_open", False))}


def hosted_mode(workspace: str | Path) -> bool:
    return read_flags(workspace).get("hosted_mode", False)


def registration_open(workspace: str | Path) -> bool:
    return read_flags(workspace).get("registration_open", False)


# ---------- users.db ----------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    pw_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'user',
    credits REAL NOT NULL DEFAULT 0,
    unlimited INTEGER NOT NULL DEFAULT 0,
    disabled INTEGER NOT NULL DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    created_at INTEGER NOT NULL,
    expires_at INTEGER NOT NULL
);
"""


def _connect(workspace: str | Path) -> sqlite3.Connection:
    db = Path(workspace) / "data" / USERS_DB
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    return conn


def _hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), _PBKDF2_ITERS)
    return f"pbkdf2${_PBKDF2_ITERS}${salt}${dk.hex()}"


def _verify_password(password: str, stored: str) -> bool:
    try:
        _, iters, salt, hexdigest = stored.split("$")
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), int(iters))
        return secrets.compare_digest(dk.hex(), hexdigest)
    except Exception:  # noqa: BLE001
        return False


def _user_row(r) -> dict:
    return {"id": r["id"], "email": r["email"], "role": r["role"],
            "credits": r["credits"], "unlimited": bool(r["unlimited"]),
            "disabled": bool(r["disabled"])}


def _new_uid() -> str:
    return "u_" + secrets.token_hex(4)


def user_count(workspace: str | Path) -> int:
    conn = _connect(workspace)
    try:
        return conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
    finally:
        conn.close()


def register_user(workspace: str | Path, email: str, password: str) -> dict:
    email = (email or "").strip().lower()
    if "@" not in email or len(email) < 5 or len(email) > 120:
        raise ValueError("invalid email")
    if len(password) < 6:
        raise ValueError("password must be at least 6 characters")
    conn = _connect(workspace)
    try:
        first = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"] == 0
        uid = _new_uid()
        conn.execute(
            "INSERT INTO users (id, email, pw_hash, role, credits, unlimited) VALUES (?,?,?,?,?,?)",
            (uid, email, _hash_password(password),
             "admin" if first else "user",
             5.0 if not first else 0.0,
             1 if first else 0))
        conn.commit()
        return {"id": uid, "email": email, "role": "admin" if first else "user",
                "credits": 5.0 if not first else 0.0,
                "unlimited": bool(first), "disabled": False}
    except sqlite3.IntegrityError:
        raise ValueError("email already registered")
    finally:
        conn.close()


def authenticate(workspace: str | Path, email: str, password: str) -> dict | None:
    conn = _connect(workspace)
    try:
        r = conn.execute("SELECT * FROM users WHERE email=?", ((email or "").strip().lower(),)).fetchone()
        if not r or r["disabled"] or not _verify_password(password, r["pw_hash"]):
            return None
        return _user_row(r)
    finally:
        conn.close()


def create_session(workspace: str | Path, user_id: str) -> str:
    token = secrets.token_urlsafe(32)
    now = int(time.time())
    conn = _connect(workspace)
    try:
        conn.execute("DELETE FROM sessions WHERE expires_at < ?", (now,))
        conn.execute("INSERT INTO sessions (token, user_id, created_at, expires_at) VALUES (?,?,?,?)",
                     (token, user_id, now, now + SESSION_TTL))
        conn.commit()
        return token
    finally:
        conn.close()


def resolve_session(workspace: str | Path, token: str) -> dict | None:
    if not token:
        return None
    conn = _connect(workspace)
    try:
        conn.execute("DELETE FROM sessions WHERE expires_at < ?", (int(time.time()),))
        r = conn.execute(
            "SELECT u.* FROM sessions s JOIN users u ON u.id = s.user_id "
            "WHERE s.token=? AND s.expires_at > ?", (token, int(time.time()))).fetchone()
        if not r or r["disabled"]:
            return None
        return _user_row(r)
    finally:
        conn.close()


def delete_session(workspace: str | Path, token: str) -> None:
    conn = _connect(workspace)
    try:
        conn.execute("DELETE FROM sessions WHERE token=?", (token,))
        conn.commit()
    finally:
        conn.close()


def list_users(workspace: str | Path) -> list[dict]:
    conn = _connect(workspace)
    try:
        return [_user_row(r) for r in conn.execute("SELECT * FROM users ORDER BY created_at")]
    finally:
        conn.close()


def add_credits(workspace: str | Path, uid: str, amount: float) -> dict | None:
    conn = _connect(workspace)
    try:
        conn.execute("UPDATE users SET credits = MAX(0, credits + ?) WHERE id=?", (float(amount), uid))
        conn.commit()
        r = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        return _user_row(r) if r else None
    finally:
        conn.close()


def set_user_flag(workspace: str | Path, uid: str, field: str, value) -> dict | None:
    assert field in ("disabled", "unlimited")
    conn = _connect(workspace)
    try:
        conn.execute(f"UPDATE users SET {field}=? WHERE id=?", (1 if value else 0, uid))
        conn.commit()
        r = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        return _user_row(r) if r else None
    finally:
        conn.close()


def consume_credit(workspace: str | Path, user: dict) -> bool:
    """True if the user may launch an episode. Admins/unlimited pass freely;
    regular users spend 1 credit. Decrement happens at launch (v1: no refund)."""
    if not user:
        return False
    if user.get("role") == "admin" or user.get("unlimited"):
        return True
    conn = _connect(workspace)
    try:
        r = conn.execute("SELECT credits FROM users WHERE id=?", (user["id"],)).fetchone()
        if not r or r["credits"] < 1:
            return False
        conn.execute("UPDATE users SET credits = credits - 1 WHERE id=?", (user["id"],))
        conn.commit()
        return True
    finally:
        conn.close()
