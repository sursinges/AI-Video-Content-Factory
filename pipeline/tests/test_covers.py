"""Cover generation tests (S5-02): provider image + title overlay in M5,
drawtext fallback, and the cover studio API endpoints. No network needed."""

import json
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from core.contracts import EpisodeManifest
from modules.base import RunContext
from modules.m5_metadata.runner import M5Metadata
from ui.server import WORKSPACE, app

client = TestClient(app)


@pytest.fixture
def workspace(tmp_path):
    src = Path(__file__).resolve().parent.parent
    (tmp_path / "config").mkdir()
    for f in ("providers.yaml", "channel.profile.yaml"):
        text = (src / "config" / f).read_text(encoding="utf-8")
        if f == "channel.profile.yaml":
            text = text.replace("default_target_minutes: 45", "default_target_minutes: 1")
            text = text.replace("chunk_chars: [6000, 9000]", "chunk_chars: [300, 600]")
        (tmp_path / "config" / f).write_text(text, encoding="utf-8")
    manifest = yaml.safe_load((src / "config" / "episode.template.yaml").read_text(encoding="utf-8"))
    manifest["run_id"] = "ep-cover"
    (tmp_path / "episode.manifest.yaml").write_text(
        yaml.safe_dump(manifest, allow_unicode=True), encoding="utf-8")
    return tmp_path


def _mini_ctx(tmp_path: Path, dry_run: bool = True) -> RunContext:
    """Minimal RunContext for direct M5 runs (mock image provider + stub inputs)."""
    from core.providers.router import Router
    from core.state import StateDB

    provs = yaml.safe_load((WORKSPACE / "config" / "providers.yaml").read_text(encoding="utf-8"))
    provs.setdefault("defaults", {})["image"] = "mock_image"
    provs["fallbacks"] = {}
    rd = tmp_path / "runs" / "ep-mini"
    (rd / "script").mkdir(parents=True, exist_ok=True)
    (rd / "audio").mkdir(parents=True, exist_ok=True)
    (rd / "script" / "script.json").write_text(json.dumps(
        {"chunks": [{"text": "Тестовый текст истории про обложку."}]}, ensure_ascii=False),
        encoding="utf-8")
    (rd / "audio" / "audio_result.json").write_text(json.dumps(
        {"duration_sec": 60.0, "parts": [30.0, 30.0]}), encoding="utf-8")
    state = StateDB(tmp_path / "state.db")
    router = Router(provs, state, "ep-mini", rd)
    return RunContext(
        manifest=EpisodeManifest(run_id="ep-mini", channel_id="test", topic="Тестовая тема обложки"),
        run_dir=rd, workspace=tmp_path,
        profile={}, router=router, state=state, library=None, dry_run=dry_run,
    )


def _meta_of(artifacts):
    return [m for rel, m in artifacts if rel == "metadata/metadata.json"][0]


def test_m5_cover_generated_with_overlay_in_dry_run(tmp_path):
    """Dry-run: mock image provider art + burned-in title (not a flat card)."""
    artifacts = M5Metadata().run(_mini_ctx(tmp_path))
    thumb = tmp_path / "runs" / "ep-mini" / "metadata" / "thumbnail.png"
    assert thumb.exists() and thumb.stat().st_size > 1000
    assert _meta_of(artifacts).thumbnail.ref, "provider path must record the cover prompt in ref"


def test_m5_cover_drawtext_fallback(tmp_path):
    """Image provider failure -> guaranteed drawtext card, no exception."""
    from core.providers.router import ProviderError

    ctx = _mini_ctx(tmp_path)

    class _BrokenRouter:
        on_event = staticmethod(lambda msg: None)

        def call(self, ptype, payload, provider_id=None, cost_usd=0.0):
            raise ProviderError("no image provider configured")

    ctx.router = _BrokenRouter()
    artifacts = M5Metadata().run(ctx)
    thumb = tmp_path / "runs" / "ep-mini" / "metadata" / "thumbnail.png"
    assert thumb.exists() and thumb.stat().st_size > 1000
    assert _meta_of(artifacts).thumbnail.ref is None  # fallback did not use a provider prompt


def test_full_dry_run_produces_cover(workspace):
    from core.orchestrator import Orchestrator

    orch = Orchestrator(workspace, on_event=lambda m: None)
    try:
        orch.run(workspace / "episode.manifest.yaml", dry_run=True)
        rd = workspace / "runs" / "ep-cover"
        assert (rd / "metadata" / "thumbnail.png").stat().st_size > 1000
        meta = json.loads((rd / "metadata" / "metadata.json").read_text(encoding="utf-8"))
        assert meta["thumbnail"]["asset"].endswith("thumbnail.png")
    finally:
        orch.close()


def test_cover_studio_generate_list_set():
    run_id = "ep-coverapi"
    rd = WORKSPACE / "runs" / run_id
    (rd / "metadata").mkdir(parents=True, exist_ok=True)
    (rd / "metadata" / "metadata.json").write_text(json.dumps(
        {"title": "Тест", "thumbnail": {"text_overlay": "TEST COVER"}}, ensure_ascii=False),
        encoding="utf-8")
    try:
        r = client.post("/api/cover/generate", json={"run_id": run_id, "provider": "mock_image"})
        assert r.status_code == 200, r.text
        cover = r.json()["path"]
        assert Path(cover).exists() and Path(cover).stat().st_size > 1000
        lst = client.get("/api/cover/list", params={"run_id": run_id}).json()
        assert lst["covers"], "generated cover must be listed"
        r2 = client.post("/api/cover/set", json={"run_id": run_id, "path": lst["covers"][0]})
        assert r2.status_code == 200
        meta = json.loads((rd / "metadata" / "metadata.json").read_text(encoding="utf-8"))
        assert meta["thumbnail"]["asset"].endswith("thumbnail.png")
    finally:
        import shutil

        shutil.rmtree(rd, ignore_errors=True)


def test_overlay_title_text_writes_in_place(tmp_path):
    from core.media import overlay_title_text

    from core.media import drawtext_card

    img = tmp_path / "base.png"
    drawtext_card(img, "BASE")
    out = overlay_title_text(img, "TITLE TEXT")
    assert out == img and img.stat().st_size > 1000
