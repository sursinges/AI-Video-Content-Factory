"""Per-scene preview endpoint (owner request): renders one scene clip at
preview resolution without the full assembly, returns a playable URL."""

import json
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ui.server import WORKSPACE, app

client = TestClient(app)


@pytest.fixture
def mini_run():
    run_id = "ep-preview-test"
    rd = WORKSPACE / "runs" / run_id
    (rd / "visual" / "assets").mkdir(parents=True, exist_ok=True)
    (rd / "visual" / "clips").mkdir(parents=True, exist_ok=True)
    (rd / "audio").mkdir(parents=True, exist_ok=True)
    (rd / "video" / "_work").mkdir(parents=True, exist_ok=True)
    img = rd / "visual" / "assets" / "s001.png"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                    "-f", "lavfi", "-i", "color=c=0x224466:s=320x180:d=1",
                    "-frames:v", "1", str(img)], check=True)
    (rd / "visual" / "scenes.json").write_text(json.dumps({"scenes": [
        {"id": "s001", "start": 0.0, "end": 1.5, "text_ref": "a", "prompt": "p",
         "seed": 1, "asset": str(img), "status": "done", "effect": "zoom_in"},
        {"id": "s002", "start": 1.5, "end": 3.0, "text_ref": "b", "prompt": "p",
         "seed": 2, "asset": str(img), "status": "done"},
    ]}), encoding="utf-8")
    (rd / "audio" / "audio_result.json").write_text(json.dumps(
        {"duration_sec": 3.0, "parts": [1.5, 1.5], "episode_path": ""}), encoding="utf-8")
    try:
        yield run_id, rd
    finally:
        import shutil

        shutil.rmtree(rd, ignore_errors=True)


def test_preview_scene_renders_playable_clip(mini_run):
    run_id, rd = mini_run
    r = client.post(f"/api/run/{run_id}/preview_scene", json={"scene_index": 0})
    assert r.status_code == 200, r.text
    url = r.json()["url"]
    local = rd / "video" / "_work" / "preview_scene.mp4"
    assert local.exists() and local.stat().st_size > 1000
    assert "/files/runs/" in url
    # ~1.9s of scene at 960x540 — fast even on CPU
    from core.media import ffprobe_duration

    assert 1.0 <= ffprobe_duration(local) <= 3.0


def test_preview_scene_range_check(mini_run):
    run_id, _ = mini_run
    r = client.post(f"/api/run/{run_id}/preview_scene", json={"scene_index": 9})
    assert r.status_code == 400


def test_preview_scene_missing_scenes():
    r = client.post("/api/run/ep-nope/preview_scene", json={"scene_index": 0})
    assert r.status_code == 404
