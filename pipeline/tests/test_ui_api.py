"""UI API hardening & feature tests (no network, no GPU): run_id guard,
token auth, notes traversal block, upload validation, visual presets overlay,
system snapshot. Covers UI-14/UI-15 waves (owner request 2026-09-27)."""

import os
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from ui.server import WORKSPACE, app

client = TestClient(app)


def test_run_id_guard_rejects_bad_id():
    r = client.get("/api/run/%21%40%24/progress")  # "!@$" is not [A-Za-z0-9._-]
    assert r.status_code == 400


def test_run_id_guard_allows_normal_id():
    r = client.get("/api/run/ep-9999/progress")
    assert r.status_code == 404  # валидный id, прогона нет


def test_notes_traversal_blocked():
    r = client.get("/api/notes/file", params={"path": "../config/providers.yaml"})
    assert r.status_code == 400


def test_notes_escape_below_root_blocked():
    r = client.get("/api/notes/file", params={"path": ".."})
    assert r.status_code == 400


def test_upload_invalid_b64_rejected():
    r = client.post("/api/upload_asset", json={"name": "x.png", "b64": "!!!not-b64!!!"})
    assert r.status_code == 400


def test_upload_empty_rejected():
    r = client.post("/api/upload_asset", json={"name": "x.png", "b64": ""})
    assert r.status_code == 400


def test_visual_presets_save_uses_custom_overlay():
    r = client.post("/api/visual_presets/save", json={
        "key": "zzz_test_preset", "preset": {"name": "Test", "style_prompt": "x"}})
    assert r.status_code == 200 and r.json().get("ok") is True
    merged = client.get("/api/visual_presets").json()
    assert "zzz_test_preset" in merged["presets"]
    assert "dark_history_cinematic" in merged["presets"]  # основные никуда не делись
    # основной YAML владельца не перезаписан
    main_text = (WORKSPACE / "config" / "visual_presets.yaml").read_text(encoding="utf-8")
    assert "zzz_test_preset" not in main_text
    # невалидный ключ отклонён
    bad = client.post("/api/visual_presets/save", json={"key": "плохой key!", "preset": {}})
    assert bad.status_code == 400
    # cleanup
    custom = WORKSPACE / "config" / "visual_presets_custom.yaml"
    if custom.exists():
        data = yaml.safe_load(custom.read_text(encoding="utf-8")) or {}
        (data.get("presets") or {}).pop("zzz_test_preset", None)
        custom.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")


def test_system_snapshot_fields():
    r = client.get("/api/system")
    assert r.status_code == 200
    body = r.json()
    for k in ("ffmpeg", "python", "runs_size", "runs_count", "cache_entries", "cache_bytes"):
        assert k in body


def test_token_auth_enforced(monkeypatch):
    monkeypatch.setenv("UI_TOKEN", "test-sekret")
    r = client.get("/api/state")
    assert r.status_code == 401
    r = client.get("/api/state", params={"token": "test-sekret"})
    assert r.status_code == 200
    r = client.get("/api/state", headers={"x-ui-token": "test-sekret"})
    assert r.status_code == 200
    monkeypatch.delenv("UI_TOKEN")


def test_m3_visual_preset_overlay(tmp_path):
    """_load_visual_preset видит пользовательский оверлей поверх основного YAML."""
    from modules.m3_visual.runner import _load_visual_preset

    assert "style_prompt" in _load_visual_preset("dark_history_cinematic")
    custom = WORKSPACE / "config" / "visual_presets_custom.yaml"
    backup = custom.read_text(encoding="utf-8") if custom.exists() else None
    try:
        custom.parent.mkdir(parents=True, exist_ok=True)
        custom.write_text(yaml.safe_dump({"presets": {"zzz_overlay_test": {
            "name": "Overlay", "style_prompt": "overlay test style",
            "negative_prompt": "nope"}}}, allow_unicode=True), encoding="utf-8")
        p = _load_visual_preset("zzz_overlay_test")
        assert p["style_prompt"] == "overlay test style"
    finally:
        if backup is None:
            custom.unlink(missing_ok=True)
        else:
            custom.write_text(backup, encoding="utf-8")


# --- wave 2 (ADD-36..40, SEC-02) ---------------------------------------------

def test_export_zip_without_video_rejected():
    r = client.get("/api/run/ep-9999/export_zip")
    assert r.status_code == 400  # валидный id, но видео не собрано


def test_metadata_endpoint():
    r = client.get("/api/run/ep-0015/metadata")
    assert r.status_code in (200, 404)
    if r.status_code == 200:
        assert "title" in r.json()


def test_ws_token_enforced(monkeypatch):
    from starlette.testclient import WebSocketDisconnect

    monkeypatch.setenv("UI_TOKEN", "ws-sekret")
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/remote") as ws:
            ws.receive_text()
    monkeypatch.delenv("UI_TOKEN")


def test_backup_helper_keeps_previous_version(tmp_path):
    from ui.server import _backup

    f = tmp_path / "x.yaml"
    f.write_text("v1", encoding="utf-8")
    _backup(f)
    f.write_text("v2", encoding="utf-8")
    assert f.with_suffix(".yaml.bak").read_text(encoding="utf-8") == "v1"


def test_motion_new_templates_available():
    from core.motion import create_project, list_templates

    ts = list_templates()
    assert "chapter_card" in ts and "outro_card" in ts
    p = create_project("t_ui_test", "chapter_card", {"TOP": "часть 1", "TITLE": "Тест", "DURATION": 2})
    import shutil

    html = (Path(p["path"]) / "composition.html").read_text(encoding="utf-8")
    assert "{{TOP}}" not in html and "часть 1" in html and "renderFrame" in html
    shutil.rmtree(p["path"], ignore_errors=True)


def test_progress_returns_log_tail():
    r = client.get("/api/run/ep-0005/progress")
    if r.status_code == 200:
        body = r.json()
        assert isinstance(body.get("log_tail"), str)


def test_motion_aspect_vertical_render():
    """9:16 create+render: config хранит аспект, mp4 реально вертикальный."""
    import shutil as sh
    import subprocess

    from core.media import ffprobe_duration
    from core.motion import create_project, render

    p = create_project("t_aspect", "chapter_card",
                       {"TOP": "часть 1", "TITLE": "Вертикаль", "DURATION": 1}, aspect="9:16")
    try:
        assert p["aspect"] == "9:16"
        r = render(p["id"])
        assert r.get("video") and ffprobe_duration(r["video"]) > 0
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
             "stream=width,height", "-of", "csv=p=0", r["video"]],
            capture_output=True, text=True)
        w, h = out.stdout.strip().split(",")
        assert (int(w), int(h)) == (1080, 1920)
    finally:
        sh.rmtree(p["path"], ignore_errors=True)


def test_ambient_synth_all_moods():
    """Процедурный эмбиент: все 6 mood синтезируются без ошибок."""
    from core.providers.ambient_synth import MOODS, AmbientSynthProvider

    p = AmbientSynthProvider("ambient_synth", "music", {}, resolve_secret=lambda r: "")
    for mood in MOODS:
        out = f"tmp_probe/test_amb_{mood}.m4a"
        r = p.execute({"out_path": out, "duration_sec": 6, "mood": mood})
        assert r.get("audio_path")


def test_music_moods_and_library():
    r = client.get("/api/music/moods")
    assert r.status_code == 200
    body = r.json()
    assert set(body["moods"]) >= {"night", "rain"}
    assert isinstance(body["tracks"], list)


def test_scheduled_endpoint():
    r = client.get("/api/scheduled")
    assert r.status_code == 200
    assert isinstance(r.json().get("scheduled"), list)


def test_search_endpoint():
    r = client.get("/api/search", params={"q": "ep"})
    assert r.status_code == 200
    assert isinstance(r.json().get("results"), list)
