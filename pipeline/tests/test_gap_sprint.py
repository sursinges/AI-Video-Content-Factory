"""GAP sprint tests (2026-10-05): ambient_synth v2 quality rebuild, music
providers (freesound, openverse registered), GAP-05 spend summary,
GAP-04 profile activation, GAP-01 image->video scaffold (mock + fal BYOK)."""

from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from ui.server import WORKSPACE, app

client = TestClient(app)


# ---------- music ----------

@pytest.mark.parametrize("mood", ["night", "rain", "wind", "drone", "fire", "space"])
def test_ambient_synth_v2_all_moods(tmp_path, mood):
    from core.providers.ambient_synth import AmbientSynthProvider
    p = AmbientSynthProvider(name="t", ptype="music", cfg={}, resolve_secret=lambda r: "")
    out = tmp_path / f"amb_{mood}.m4a"
    r = p.execute({"out_path": str(out), "mood": mood, "duration_sec": 8})
    assert Path(r["audio_path"]).exists() and Path(r["audio_path"]).stat().st_size > 10_000


def test_freesound_no_token_clean_error(tmp_path):
    from core.providers.freesound_music import FreesoundMusicProvider
    from core.providers.router import ProviderError
    p = FreesoundMusicProvider(name="f", ptype="music", cfg={"api_key_ref": "FREESOUND_TOKEN"},
                               resolve_secret=lambda r: "")
    with pytest.raises(ProviderError) as e:
        p.execute({"out_path": str(tmp_path / "t.mp3"), "mood": "night"})
    assert "FREESOUND_TOKEN" in str(e.value)


def test_registry_has_new_music_and_video_providers():
    from core.providers.router import build_registry, load_providers_config
    cfg = load_providers_config(WORKSPACE / "config" / "providers.yaml")
    reg = build_registry(cfg, lambda r: "")
    assert "music/freesound_music" in reg
    assert "music/openverse_music" in reg
    assert "video/mock_video" in reg
    assert "video/fal_video" in reg


def test_catalog_lists_openverse_and_fal():
    r = client.get("/api/provider_catalog")
    assert r.status_code == 200
    ids = {c["id"] for c in r.json()["catalog"]}
    assert {"jamendo", "openverse", "freesound", "fal_ai"} <= ids


# ---------- GAP-01: image->video scaffold ----------

def test_mock_video_produces_real_mp4(tmp_path):
    from core.providers.mock import MockProvider
    m = MockProvider(name="mock_video", ptype="video", cfg={}, resolve_secret=lambda r: "")
    out = tmp_path / "v.mp4"
    r = m.execute({"out_path": str(out), "duration_sec": 1})
    assert Path(r["video_path"]).exists() and Path(r["video_path"]).stat().st_size > 1000


def test_fal_video_no_key_clean_error(tmp_path):
    from core.providers.fal_video import FalVideoProvider
    from core.providers.router import ProviderError
    f = FalVideoProvider(name="fal_video", ptype="video", cfg={"api_key_ref": "FAL_KEY"},
                         resolve_secret=lambda r: "")
    with pytest.raises(ProviderError) as e:
        f.execute({"out_path": str(tmp_path / "v.mp4"), "image_path": ""})
    assert "FAL_KEY" in str(e.value)


# ---------- GAP-05: channel spend summary ----------

def test_spend_summary_shape():
    r = client.get("/api/spend/summary")
    assert r.status_code == 200
    data = r.json()
    for scope in ("month", "all"):
        for field in ("calls", "tokens", "cost", "episodes", "minutes"):
            assert field in data[scope]
    assert isinstance(data["top"], list)


# ---------- GAP-04: profile activation ----------

def test_profile_activate_missing_404():
    r = client.post("/api/profiles/activate", json={"name": "zz_no_such_profile"})
    assert r.status_code == 404


def test_profile_activate_bad_name_400():
    r = client.post("/api/profiles/activate", json={"name": "bad name!"})
    assert r.status_code == 400


def test_profile_activate_roundtrip_restores():
    prof_dir = WORKSPACE / "config" / "profiles"
    prof_dir.mkdir(exist_ok=True)
    src = prof_dir / "zz_gap04_test.yaml"
    original = (WORKSPACE / "config" / "channel.profile.yaml").read_text(encoding="utf-8")
    try:
        src.write_text(original + "\n# gap04 test marker\n", encoding="utf-8")
        r = client.post("/api/profiles/activate", json={"name": "zz_gap04_test"})
        assert r.status_code == 200 and r.json()["ok"] is True
        cur = (WORKSPACE / "config" / "channel.profile.yaml").read_text(encoding="utf-8")
        assert "gap04 test marker" in cur
        # .bak of the previous active profile must exist and hold the original
        bak = (WORKSPACE / "config" / "channel.profile.yaml.bak").read_text(encoding="utf-8")
        assert bak == original
    finally:
        (WORKSPACE / "config" / "channel.profile.yaml").write_text(original, encoding="utf-8")
        if src.exists():
            src.unlink()
