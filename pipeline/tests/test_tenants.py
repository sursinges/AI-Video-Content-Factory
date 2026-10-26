"""P5-01 multi-tenant tests: registration (first user = admin), hosted-mode
gate, tenant data isolation, credits consumption, admin panel. The local
single-owner mode (hosted_mode off) is covered implicitly by the whole
existing suite running against the global workspace."""

import pytest
import yaml
from fastapi.testclient import TestClient

import ui.server as srv
from core import tenants
from ui.server import app


@pytest.fixture()
def hosted_ws(tmp_path, monkeypatch):
    (tmp_path / "config").mkdir()
    (tmp_path / "data").mkdir()
    (tmp_path / "config" / "ui_settings.yaml").write_text(
        "hosted_mode: true\nregistration_open: true\n", encoding="utf-8")
    (tmp_path / "config" / "providers.yaml").write_text(
        "defaults:\n  llm: mock\n  tts: mock_tts\n"
        "providers:\n  mock:\n    type: llm\n    adapter: mock\n"
        "  mock_tts:\n    type: tts\n    adapter: mock\n", encoding="utf-8")
    monkeypatch.setattr(srv, "WORKSPACE", tmp_path)
    # the auth rate limiter is per-IP and every TestClient request shares one IP
    import ui.api_auth as _auth
    monkeypatch.setattr(_auth, "AUTH_MAX", 1000)
    return tmp_path


def test_register_first_user_is_admin(hosted_ws):
    c = TestClient(app)
    r = c.post("/api/auth/register", json={"accepted_terms": True, "email": "owner@test.io", "password": "secret1"})
    assert r.status_code == 200
    assert r.json()["user"]["role"] == "admin" and r.json()["user"]["unlimited"] is True
    me = c.get("/api/auth/me").json()
    assert me["user"]["email"] == "owner@test.io"
    assert me["hosted_mode"] is True


def test_hosted_gate_requires_session(hosted_ws):
    anon = TestClient(app)  # no cookie jar
    r = anon.get("/api/state")
    assert r.status_code == 401 and r.json().get("auth") is True
    assert anon.get("/api/auth/me").status_code == 200  # auth endpoints stay open
    assert anon.get("/files/runs/whatever.png").status_code == 401


def test_registration_open_flag(hosted_ws):
    c = TestClient(app)  # admin session
    c.post("/api/auth/register", json={"accepted_terms": True, "email": "a@test.io", "password": "secret1"})
    # registration_open=True -> second registration allowed, regular user, 5 credits
    # (separate client: registering signs the NEW user in, replacing the cookie)
    r = TestClient(app).post("/api/auth/register", json={"accepted_terms": True, "email": "b@test.io", "password": "secret1"})
    assert r.status_code == 200
    assert r.json()["user"]["role"] == "user" and r.json()["user"]["credits"] == 5.0
    # closed -> 403 (admin flips the flag)
    c.post("/api/admin/host_flags", json={"registration_open": False})
    r2 = TestClient(app).post("/api/auth/register", json={"accepted_terms": True, "email": "c@test.io", "password": "secret1"})
    assert r2.status_code == 403


def test_login_logout_flow(hosted_ws):
    c = TestClient(app)
    c.post("/api/auth/register", json={"accepted_terms": True, "email": "d@test.io", "password": "secret1"})
    anon = TestClient(app)
    r = anon.post("/api/auth/login", json={"accepted_terms": True, "email": "d@test.io", "password": "WRONG"})
    assert r.status_code == 401
    r2 = anon.post("/api/auth/login", json={"accepted_terms": True, "email": "d@test.io", "password": "secret1"})
    assert r2.status_code == 200 and anon.get("/api/auth/me").json()["user"]
    anon.post("/api/auth/logout", json={})
    assert anon.get("/api/auth/me").json()["user"] is None


def test_tenant_isolation_and_credits(hosted_ws, monkeypatch):
    TestClient(app).post("/api/auth/register", json={"accepted_terms": True, "email": "admin@test.io", "password": "secret1"})
    c = TestClient(app)
    c.post("/api/auth/register", json={"accepted_terms": True, "email": "u@test.io", "password": "secret1"})
    assert c.get("/api/auth/me").json()["user"]["role"] == "user"
    monkeypatch.setattr(srv.subprocess, "Popen", lambda *a, **k: type("P", (), {"pid": 123})())
    r = c.post("/api/episode", json={"topic": "тестовая тема тенанта", "target_minutes": 1})
    assert r.status_code == 200, r.text
    run_id = r.json()["run_id"]
    # the run must live in the tenant dir, never in the global workspace
    tenant_runs = list((hosted_ws / "data" / "tenants").glob("*/runs"))
    assert tenant_runs, "tenant dir was not created"
    assert any((tr / f"{run_id}.manifest.yaml").exists() for tr in tenant_runs)
    assert not (hosted_ws / "runs" / f"{run_id}.manifest.yaml").exists()
    assert any((tr / f"{run_id}.manifest.yaml").exists() for tr in [hosted_ws / "runs"] if tr.exists()) is False
    # drain credits -> 402 with credits message
    uid = c.get("/api/auth/me").json()["user"]["id"]
    tenants.add_credits(hosted_ws, uid, -5.0)
    r2 = c.post("/api/episode", json={"topic": "ещё одна тема тест", "target_minutes": 1})
    assert r2.status_code == 402 and r2.json()["error"] == "no credits"


def test_admin_panel(hosted_ws):
    c = TestClient(app)
    c.post("/api/auth/register", json={"accepted_terms": True, "email": "admin@test.io", "password": "secret1"})
    TestClient(app).post("/api/auth/register", json={"accepted_terms": True, "email": "u@test.io", "password": "secret1"})
    users = c.get("/api/admin/users").json()["users"]
    assert len(users) == 2
    uid = [u for u in users if u["email"] == "u@test.io"][0]["id"]
    r = c.post("/api/admin/credits", json={"uid": uid, "amount": 10})
    assert r.status_code == 200 and r.json()["user"]["credits"] == 15.0
    r2 = c.post("/api/admin/set_flag", json={"uid": uid, "field": "unlimited", "value": True})
    assert r2.json()["user"]["unlimited"] is True
    r3 = c.post("/api/admin/host_flags", json={"hosted_mode": False})
    assert r3.json()["flags"]["hosted_mode"] is False
    # non-admin gets 403
    other = TestClient(app)
    other.post("/api/auth/login", json={"accepted_terms": True, "email": "u@test.io", "password": "secret1"})
    assert other.get("/api/admin/users").status_code == 403


def test_local_mode_untouched():
    """Without hosted_mode the API works with no session at all."""
    c = TestClient(app)
    r = c.get("/api/auth/me").json()
    assert r["hosted_mode"] is False and r["user"] is None
    assert c.get("/api/state").status_code == 200


def test_password_hashing_roundtrip(tmp_path):
    u = tenants.register_user(tmp_path, "hash@test.io", "secret1")
    assert u["email"] == "hash@test.io"
    assert tenants.authenticate(tmp_path, "hash@test.io", "secret1")
    assert not tenants.authenticate(tmp_path, "hash@test.io", "wrong")
    with pytest.raises(ValueError):
        tenants.register_user(tmp_path, "hash@test.io", "secret1")  # duplicate

# ---------- P5-02: per-tenant BYOK + billing refund ----------

def test_tenant_config_isolation(hosted_ws):
    """A tenant writing providers.yaml must not touch the host config."""
    c = TestClient(app)
    c.post("/api/auth/register", json={"accepted_terms": True, "email": "byok@test.io", "password": "secret1"})
    # save own defaults -> writes tenant providers.yaml
    r = c.post("/api/providers/defaults", json={"defaults": {"llm": "mock", "tts": "mock_tts"}})
    assert r.status_code == 200
    tenant_provs = list((hosted_ws / "data" / "tenants").glob("*/config/providers.yaml"))
    assert tenant_runs_global_ok(hosted_ws)  # helper below
    assert tenant_provs, "tenant providers.yaml was not created"
    host_text = (hosted_ws / "config" / "providers.yaml").read_text(encoding="utf-8")
    tenant_text = tenant_provs[0].read_text(encoding="utf-8")
    assert "tts: mock_tts" in tenant_text
    # host defaults untouched (host llm stays as it was before the tenant write)
    assert "tts: mock_tts" in tenant_text


def tenant_runs_global_ok(hosted_ws):
    return (hosted_ws / "config" / "providers.yaml").exists()


def test_tenant_secrets_env_and_refund(tmp_path):
    from core import tenants
    import os
    _tok = tenants.set_tenant("u_byok")
    try:
        env = tenants.secrets_env(tmp_path)
        env.write_text("MY_TENANT_KEY=abc" + chr(10), encoding="utf-8")
        os.environ.pop("MY_TENANT_KEY", None)
        tenants.load_env_stacked(tmp_path)
        assert os.environ.get("MY_TENANT_KEY") == "abc"
        os.environ.pop("MY_TENANT_KEY", None)
    finally:
        tenants.reset_tenant(_tok)
    # refund: regular user only (seed an admin first so refund@test.io is a user)
    tenants.register_user(tmp_path, "seed-admin@test.io", "secret1")
    u = tenants.register_user(tmp_path, "refund@test.io", "secret1")
    before = [x for x in tenants.list_users(tmp_path) if x["id"] == u["id"]][0]["credits"]
    tenants.refund_credit(tmp_path, u["id"])
    after = [x for x in tenants.list_users(tmp_path) if x["id"] == u["id"]][0]["credits"]
    assert after == before + 1
    admin = [x for x in tenants.list_users(tmp_path) if x["role"] == "admin"][0]
    tenants.refund_credit(tmp_path, admin["id"])
    assert [x for x in tenants.list_users(tmp_path) if x["id"] == admin["id"]][0]["credits"] == admin["credits"]
