"""Batch-2 tests: MCP stdio server protocol, run-workspace endpoints
(script_save, scene_voice), VoiceStudio voice registration."""

import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from ui.server import WORKSPACE, app

client = TestClient(app)


# ---------- MCP stdio server ----------

def test_mcp_server_stdio_protocol():
    """initialize -> tools/list -> tools/call(doctor) over line JSON-RPC."""
    server = Path(__file__).resolve().parents[1] / "tools" / "mcp_server.py"
    proc = subprocess.Popen([sys.executable, "-X", "utf8", str(server)],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, text=True, encoding="utf-8")
    try:
        reqs = [
            json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}),
            json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}),
            json.dumps({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                        "params": {"name": "doctor", "arguments": {}}}),
        ]
        out, _ = proc.communicate("\n".join(reqs) + "\n", timeout=60)
        lines = [json.loads(l) for l in out.strip().splitlines() if l.strip()]
        by_id = {r.get("id"): r for r in lines}
        assert by_id[1]["result"]["serverInfo"]["name"] == "pipeline"
        names = [t["name"] for t in by_id[2]["result"]["tools"]]
        for tool in ("list_runs", "run_status", "create_episode", "resume_run", "doctor"):
            assert tool in names
        doctor = json.loads(by_id[3]["result"]["content"][0]["text"])
        assert doctor["overall"] in ("ok", "warning", "error")
    finally:
        proc.kill()


def test_mcp_clients_endpoint():
    from ui.server import _ui_token  # real .env may carry UI_TOKEN

    r = client.get("/api/mcp/clients")
    if r.status_code == 401:
        client2 = TestClient(app)
        r = client2.get("/api/mcp/clients", params={"token": _ui_token()})
    assert r.status_code == 200
    body = r.json()
    for k in ("claude_desktop", "claude_code", "codex", "zcode"):
        assert k in body and body[k]["config"]
    assert "resume_run" in body["tools"]


# ---------- run workspace endpoints ----------

@pytest.fixture
def mini_run():
    run_id = "ep-ws-test"
    rd = WORKSPACE / "runs" / run_id
    (rd / "script").mkdir(parents=True, exist_ok=True)
    (rd / "visual" / "assets").mkdir(parents=True, exist_ok=True)
    (rd / "audio").mkdir(parents=True, exist_ok=True)
    (rd / "script" / "script.json").write_text(json.dumps(
        {"chunks": [{"part": 1, "text": "Первая часть."}, {"part": 2, "text": "Вторая часть."}]},
        ensure_ascii=False), encoding="utf-8")
    (rd / "visual" / "scenes.json").write_text(json.dumps({"scenes": [
        {"id": "s001", "start": 0.0, "end": 1.5, "text_ref": "текст сцены один",
         "prompt": "p", "seed": 1, "status": "done"},
    ]}), encoding="utf-8")
    (rd / "audio" / "audio_result.json").write_text(json.dumps(
        {"duration_sec": 3.0, "parts": [3.0], "episode_path": ""}), encoding="utf-8")
    try:
        yield run_id, rd
    finally:
        import shutil

        shutil.rmtree(rd, ignore_errors=True)


def test_script_save_updates_chunks(mini_run):
    run_id, rd = mini_run
    r = client.post(f"/api/run/{run_id}/script_save", json={
        "chunks": [{"text": "Первая часть — отредактирована."}, {"text": "Вторая часть."}]})
    assert r.status_code == 200
    data = json.loads((rd / "script" / "script.json").read_text(encoding="utf-8"))
    assert data["chunks"][0]["text"] == "Первая часть — отредактирована."


def test_script_save_rejects_mismatch(mini_run):
    run_id, _ = mini_run
    r = client.post(f"/api/run/{run_id}/script_save", json={"chunks": [{"text": "x"}]})
    assert r.status_code == 400


def test_scene_voice_persists_choice(mini_run):
    run_id, rd = mini_run
    # mock tts provider must exist in the registry for a clean audition
    r = client.post(f"/api/run/{run_id}/scene_voice", json={
        "scene_index": 0, "provider": "mock_tts", "voice": "narrator-1"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["voice"] == {"provider": "mock_tts", "voice": "narrator-1"}
    scenes = json.loads((rd / "visual" / "scenes.json").read_text(encoding="utf-8"))["scenes"]
    assert scenes[0]["voice"]["voice"] == "narrator-1"


def test_scene_voice_unknown_provider(mini_run):
    run_id, _ = mini_run
    r = client.post(f"/api/run/{run_id}/scene_voice", json={
        "scene_index": 0, "provider": "no_such_tts"})
    assert r.status_code == 400


# ---------- VoiceStudio voice registration ----------

def test_voices_add_voice_studio_entry():
    r = client.post("/api/voices/add", json={
        "id": "vs narrator", "name": "VS Narrator", "engine": "voice_studio",
        "voice": "alloy"})
    assert r.status_code == 200
    voices = client.get("/api/voices").json()["voices"]
    entry = next(v for v in voices if v["id"] == "vs_narrator")
    assert entry["engine"] == "voice_studio" and entry["voice"] == "alloy"
    # cleanup
    client.post("/api/voices/delete", json={"id": "vs_narrator"})
