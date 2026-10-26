"""Unit tests for the system diagnostics and health check module."""

from pathlib import Path
from core.diagnostics import (
    check_python,
    check_ffmpeg,
    check_disk_space,
    check_core_packages,
    check_configs,
    run_diagnostics,
)


def test_check_python():
    res = check_python()
    assert res["status"] in ("ok", "warning", "error")
    assert "version" in res
    assert res["version"] is not None


def test_check_disk_space(tmp_path):
    res = check_disk_space(tmp_path)
    assert res["status"] in ("ok", "warning", "error")
    assert "GB free" in res["detail"]


def test_check_core_packages():
    res = check_core_packages()
    assert res["status"] == "ok"
    assert "pydantic" in res["detail"]


def test_check_configs(tmp_path):
    # Test missing configs
    reports = check_configs(tmp_path)
    assert any(r["status"] == "error" for r in reports)

    # Test valid config
    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir()
    (cfg_dir / "providers.yaml").write_text("defaults: {}\nproviders: {}\n", encoding="utf-8")
    (cfg_dir / "channel.profile.yaml").write_text("name: Test Channel\n", encoding="utf-8")
    (cfg_dir / "formats.yaml").write_text("sleep_history: {}\n", encoding="utf-8")

    reports = check_configs(tmp_path)
    assert all(r["status"] == "ok" for r in reports if r["name"] != "Visual Presets")


def test_run_diagnostics():
    workspace = Path(__file__).resolve().parent.parent
    report = run_diagnostics(workspace)
    assert report["overall"] in ("ok", "warning", "error")
    assert len(report["checks"]) >= 5
