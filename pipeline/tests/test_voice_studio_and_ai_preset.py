"""VoiceStudio local TTS adapter (AGPL app, HTTP boundary) and the AI style
co-author endpoint (visual preset generation)."""

import pytest
import yaml
from fastapi.testclient import TestClient

from core.providers.router import ProviderError, build_registry
from ui.server import WORKSPACE, app

client = TestClient(app)


def _provider(monkeypatch, key: str = "vs-key"):
    monkeypatch.setenv("VOICESTUDIO_API_KEY", key)
    provs = yaml.safe_load((WORKSPACE / "config" / "providers.yaml").read_text(encoding="utf-8"))
    reg = build_registry(provs, lambda ref: {"VOICESTUDIO_API_KEY": key}.get(ref, ""))
    return reg["tts/voice_studio"]


def test_registry_has_voice_studio(monkeypatch):
    p = _provider(monkeypatch)
    assert p.adapter == "voice_studio" and p.ptype == "tts"


def test_voice_studio_synthesizes(monkeypatch, tmp_path):
    p = _provider(monkeypatch)
    captured = {}

    class _Resp:
        status_code = 200
        content = b"RIFFfake-wav-bytes"

        def raise_for_status(self):
            pass

    def fake_post(url, headers=None, json=None, timeout=None):
        captured.update(url=url, headers=headers, json=json)
        return _Resp()

    import core.providers.voice_studio as vs

    monkeypatch.setattr(vs.httpx, "post", fake_post)
    out = tmp_path / "seg.wav"
    res = p.execute({"text": "Привет из VoiceStudio", "out_path": str(out)})
    assert res["audio_path"] == str(out)
    assert out.read_bytes() == b"RIFFfake-wav-bytes"
    assert captured["url"].endswith("/v1/audio/speech")
    assert captured["headers"]["Authorization"] == "Bearer vs-key"
    assert captured["json"]["input"] == "Привет из VoiceStudio"
    assert captured["json"]["response_format"] == "wav"


def test_voice_studio_missing_key(monkeypatch, tmp_path):
    monkeypatch.delenv("VOICESTUDIO_API_KEY", raising=False)
    p = _provider(monkeypatch, key="")
    with pytest.raises(ProviderError, match="VOICESTUDIO_API_KEY"):
        p.execute({"text": "x", "out_path": str(tmp_path / "a.wav")})


def test_voice_studio_backend_down(monkeypatch, tmp_path):
    p = _provider(monkeypatch)

    def fake_post(url, headers=None, json=None, timeout=None):
        raise ConnectionError("connection refused")

    import core.providers.voice_studio as vs

    monkeypatch.setattr(vs.httpx, "post", fake_post)
    with pytest.raises(ProviderError, match="cannot reach backend"):
        p.execute({"text": "x", "out_path": str(tmp_path / "a.wav")})


@pytest.fixture(autouse=True)
def _open_api(monkeypatch):
    """This machine's real .env carries UI_TOKEN and ui_settings has the web
    edition armed — keep the API open for these endpoint tests."""
    import ui.server as srv
    from core import tenants

    monkeypatch.setattr(srv, "_ui_token", lambda: "")
    monkeypatch.setattr(tenants, "hosted_mode", lambda ws: False)


def test_ai_preset_generate_validation():
    r = client.post("/api/visual_preset/ai_generate", json={"description": "ab"})
    assert r.status_code == 400


def test_ai_preset_generate_fallback_draft():
    """No LLM key configured -> deterministic fallback draft, still usable."""
    r = client.post("/api/visual_preset/ai_generate",
                    json={"description": "warm sunrise light, film grain, minimalism"})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    pr = body["preset"]
    for k in ("name", "style_prompt", "negative_prompt", "quality_tags"):
        assert k in pr and pr[k]
    assert "warm sunrise" in pr["style_prompt"]
