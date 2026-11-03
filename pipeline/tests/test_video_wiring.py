"""GAP-01 image->video wiring tests: scene contract, mock-video clips through
the full dry run, and the M4 normalization helper. No keys, no GPU."""

import json
from pathlib import Path

import pytest
import yaml

from core.contracts import Scene
from core.media import ffprobe_duration, normalize_scene_video
from core.orchestrator import Orchestrator


def test_scene_contract_accepts_video_fields():
    sc = Scene(id="s001", start=0.0, end=10.0, text_ref="t", prompt="p", seed=1,
               motion="video", video_asset="runs/x/visual/clips/s001.mp4",
               clip_duration_sec=10.0)
    assert sc.motion == "video" and sc.effect is None
    # legacy shape (no new keys) stays valid
    old = Scene(id="s002", start=10.0, end=20.0, text_ref="t", prompt="p", seed=2)
    assert old.motion == "still" and old.video_asset is None


def test_normalize_scene_video_pads_and_resizes(tmp_path):
    src = tmp_path / "clip.mp4"
    import subprocess

    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                    "-f", "lavfi", "-i", "color=c=0x224488:s=640x360:d=1.0:r=25",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(src)], check=True)
    out = tmp_path / "norm.mp4"
    normalize_scene_video(src, out, duration=3.0, size="1920x1080")
    assert 2.9 <= ffprobe_duration(out) <= 3.3


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
    manifest["run_id"] = "ep-vid"
    manifest["overrides"] = {"provider_overrides": {"video": "mock_video"},
                             "visual": {"video_scenes": "all"}}
    (tmp_path / "episode.manifest.yaml").write_text(
        yaml.safe_dump(manifest, allow_unicode=True), encoding="utf-8")
    return tmp_path


def test_dry_run_generates_clips_and_assembles(workspace):
    orch = Orchestrator(workspace, on_event=lambda m: None)
    try:
        orch.run(workspace / "episode.manifest.yaml", dry_run=True)
        rd = workspace / "runs" / "ep-vid"
        scenes = json.loads((rd / "visual" / "scenes.json").read_text(encoding="utf-8"))["scenes"]
        assert scenes and all(sc["motion"] == "video" for sc in scenes)
        clips = list((rd / "visual" / "clips").glob("s*.mp4"))
        assert clips, "video clips must be generated for video scenes"
        for sc in scenes:
            assert sc["video_asset"] and Path(sc["video_asset"]).exists()
        effects = json.loads((rd / "video" / "effects_report.json").read_text(encoding="utf-8"))
        assert all(e["effect"] == "video_clip" for e in effects)
        assert (rd / "video" / "episode.mp4").exists()
        result = json.loads((rd / "video" / "assembly_result.json").read_text(encoding="utf-8"))
        assert result["duration_sec"] > 0
    finally:
        orch.close()


def test_default_video_mode_keeps_stills(tmp_path):
    """Without visual.video_scenes the pipeline behaves exactly as before."""
    src = Path(__file__).resolve().parent.parent
    (tmp_path / "config").mkdir()
    for f in ("providers.yaml", "channel.profile.yaml"):
        text = (src / "config" / f).read_text(encoding="utf-8")
        if f == "channel.profile.yaml":
            text = text.replace("default_target_minutes: 45", "default_target_minutes: 1")
            text = text.replace("chunk_chars: [6000, 9000]", "chunk_chars: [300, 600]")
        (tmp_path / "config" / f).write_text(text, encoding="utf-8")
    manifest = yaml.safe_load((src / "config" / "episode.template.yaml").read_text(encoding="utf-8"))
    manifest["run_id"] = "ep-still"
    (tmp_path / "episode.manifest.yaml").write_text(
        yaml.safe_dump(manifest, allow_unicode=True), encoding="utf-8")
    orch = Orchestrator(tmp_path, on_event=lambda m: None)
    try:
        orch.run(tmp_path / "episode.manifest.yaml", dry_run=True)
        scenes = json.loads(
            (tmp_path / "runs" / "ep-still" / "visual" / "scenes.json").read_text(encoding="utf-8"))["scenes"]
        assert all(sc["motion"] == "still" and not sc["video_asset"] for sc in scenes)
        assert not list((tmp_path / "runs" / "ep-still" / "visual" / "clips").glob("*.mp4"))
    finally:
        orch.close()
