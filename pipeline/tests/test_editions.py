"""Edition split (desktop vs web): resolution order, desktop forcing the
hosted machinery off, web arming it, and the public edition endpoints."""

import pytest
import yaml
from fastapi.testclient import TestClient

from core import edition, tenants
from ui.server import app

client = TestClient(app)


def _cfg(tmp_path, **kv):
    d = tmp_path / "config"
    d.mkdir(exist_ok=True)
    (d / "ui_settings.yaml").write_text(yaml.safe_dump(kv), encoding="utf-8")
    return tmp_path


def test_default_edition_is_desktop(tmp_path):
    assert edition.current(tmp_path) == "desktop"
    assert edition.is_desktop(tmp_path) and not edition.is_web(tmp_path)


def test_config_selects_web(tmp_path):
    _cfg(tmp_path, edition="web")
    assert edition.current(tmp_path) == "web"


def test_env_overrides_config(monkeypatch, tmp_path):
    _cfg(tmp_path, edition="desktop")
    monkeypatch.setenv("PIPELINE_EDITION", "web")
    assert edition.current(tmp_path) == "web"
    monkeypatch.setenv("PIPELINE_EDITION", "bogus")
    assert edition.current(tmp_path) == "desktop"
    monkeypatch.delenv("PIPELINE_EDITION")


def test_desktop_forces_hosted_machinery_off(tmp_path):
    """Even with hosted_mode: true on disk, desktop has no sign-in/credits/queue."""
    _cfg(tmp_path, edition="desktop", hosted_mode=True, registration_open=True)
    assert tenants.read_flags(tmp_path) == {"hosted_mode": False, "registration_open": False}
    assert tenants.hosted_mode(tmp_path) is False


def test_web_arms_hosted_when_flagged(tmp_path):
    _cfg(tmp_path, edition="web", hosted_mode=True, registration_open=True)
    flags = tenants.read_flags(tmp_path)
    assert flags == {"hosted_mode": True, "registration_open": True}


def test_web_without_hosted_flag_stays_open(tmp_path):
    """edition=web alone does not arm the gate — hosted_mode is the trigger."""
    _cfg(tmp_path, edition="web")
    assert tenants.hosted_mode(tmp_path) is False


def test_broken_settings_fall_back_to_desktop(tmp_path):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "ui_settings.yaml").write_text("edition: [unclosed", encoding="utf-8")
    assert edition.current(tmp_path) == "desktop"
    assert tenants.hosted_mode(tmp_path) is False


def test_api_edition_endpoint_public():
    r = client.get("/api/edition")
    assert r.status_code == 200
    body = r.json()
    assert body["edition"] in ("desktop", "web")
    assert "hosted_mode" in body and "registration_open" in body


def test_api_auth_me_reports_edition():
    r = client.get("/api/auth/me")
    assert r.status_code == 200
    assert r.json()["edition"] in ("desktop", "web")


def test_doctor_reports_edition():
    from core.diagnostics import run_diagnostics
    from pathlib import Path

    ws = Path(__file__).resolve().parent.parent
    report = run_diagnostics(ws)
    ed_checks = [c for c in report["checks"] if c["name"] == "Edition"]
    assert ed_checks and ed_checks[0]["version"] in ("desktop", "web")
