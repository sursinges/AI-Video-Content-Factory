"""P5 preview flow: draft plan (script + scenes WITHOUT synthesis/render) and
the render endpoint logic (reset draft m2/m3 -> real rerun)."""

import json
from pathlib import Path

import pytest
import yaml

from core.orchestrator import Orchestrator


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
    manifest["run_id"] = "ep-draft"
    manifest["overrides"] = {"draft_plan": True, "visual": {"plan_only": True}}
    (tmp_path / "episode.manifest.yaml").write_text(
        yaml.safe_dump(manifest, allow_unicode=True), encoding="utf-8")
    return tmp_path


def test_draft_plan_without_render(workspace):
    """Draft until m3_visual: script + estimated timings + scene plan exist;
    no audio files, no generated images, no video — and the plan is editable
    material for the real render."""
    orch = Orchestrator(workspace, lang="ru")
    try:
        run_id = orch.run(workspace / "episode.manifest.yaml", until="m3_visual", dry_run=True)
        rd = workspace / "runs" / run_id
        # script + plan exist
        script = json.loads((rd / "script" / "script.json").read_text(encoding="utf-8"))
        assert script["chunks"], "draft script chunks missing"
        scenes = json.loads((rd / "visual" / "scenes.json").read_text(encoding="utf-8"))["scenes"]
        assert scenes and all(sc["status"] == "planned" for sc in scenes)
        assert all(sc["end"] > sc["start"] for sc in scenes)
        # estimated audio result: engine=draft, no file
        audio = json.loads((rd / "audio" / "audio_result.json").read_text(encoding="utf-8"))
        assert audio["engine"] == "draft" and not audio["episode_path"]
        assert not list((rd / "audio").glob("*.wav"))
        assert not (rd / "video" / "episode.mp4").exists()
    finally:
        orch.close()


def test_render_after_draft_reruns_m2_m3(workspace, monkeypatch):
    """Simulate the /api/run/{id}/render logic: strip draft overrides, reset
    m2/m3 steps + artifacts, resume -> real synthesis replaces the estimates."""
    orch = Orchestrator(workspace, lang="ru")
    try:
        run_id = orch.run(workspace / "episode.manifest.yaml", until="m3_visual", dry_run=True)
        rd = workspace / "runs" / run_id
        assert audio["engine"] == "draft" if (audio := json.loads(
            (rd / "audio" / "audio_result.json").read_text(encoding="utf-8"))) else False

        # --- the render endpoint's reset logic ---
        st = orch.state
        row = st.get_run(run_id)
        manifest = json.loads(row["manifest"])
        manifest["overrides"].pop("draft_plan", None)
        (manifest["overrides"].get("visual") or {}).pop("plan_only", None)
        st.conn.execute("UPDATE runs SET manifest=? WHERE run_id=?",
                        (json.dumps(manifest, ensure_ascii=False), run_id))
        st.conn.execute("DELETE FROM steps WHERE run_id=? AND step IN ('m2_audio','m3_visual')", (run_id,))
        st.conn.commit()
        import shutil
        for sub in ("subtitles", "visual", "audio"):
            shutil.rmtree(rd / sub, ignore_errors=True)

        orch2 = Orchestrator(workspace, lang="ru")
        try:
            orch2.resume(run_id, dry_run=True)
            audio2 = json.loads((rd / "audio" / "audio_result.json").read_text(encoding="utf-8"))
            assert audio2["engine"] != "draft"          # real synthesis ran
            scenes2 = json.loads((rd / "visual" / "scenes.json").read_text(encoding="utf-8"))["scenes"]
            assert all(sc["status"] == "done" for sc in scenes2)  # images generated
            assert (rd / "video" / "episode.mp4").exists()        # full assembly
        finally:
            orch2.close()
    finally:
        orch.close()
