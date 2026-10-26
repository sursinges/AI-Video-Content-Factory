"""End-to-end dry-run: all steps pass without keys/network; resume re-runs
only failed steps (S0-06, S0-07 acceptance)."""

import json
from pathlib import Path

import pytest
import yaml

from core.orchestrator import Orchestrator

EXPECTED_ARTIFACTS = [
    "script/script.json",
    "audio/speechplan.json",
    "subtitles/subtitles.json",
    "visual/world.json",
    "visual/scenes.json",
    "video/assembly_result.json",
    "metadata/metadata.json",
    "publish_result.json",
]


@pytest.fixture
def workspace(tmp_path):
    src = Path(__file__).resolve().parent.parent
    (tmp_path / "config").mkdir()
    for f in ("providers.yaml", "channel.profile.yaml"):
        text = (src / "config" / f).read_text(encoding="utf-8")
        if f == "channel.profile.yaml":
            # tiny test profile: 3 short chunks -> fast real ffmpeg rendering
            text = text.replace("default_target_minutes: 45", "default_target_minutes: 1")
            text = text.replace("chunk_chars: [6000, 9000]", "chunk_chars: [300, 600]")
        (tmp_path / "config" / f).write_text(text, encoding="utf-8")
    manifest = yaml.safe_load((src / "config" / "episode.template.yaml").read_text(encoding="utf-8"))
    manifest["run_id"] = "ep-test"
    (tmp_path / "episode.manifest.yaml").write_text(
        yaml.safe_dump(manifest, allow_unicode=True), encoding="utf-8")
    return tmp_path


def test_full_dry_run(workspace):
    orch = Orchestrator(workspace, on_event=lambda m: None)
    try:
        run_id = orch.run(workspace / "episode.manifest.yaml", dry_run=True)
        assert run_id == "ep-test"
        run_dir = workspace / "runs" / "ep-test"
        for rel in EXPECTED_ARTIFACTS:
            assert (run_dir / rel).exists(), f"missing artifact {rel}"
        # usage.jsonl may be absent (no external calls in S0 stubs) — fine
        st = orch.status("ep-test")[0]
        assert st["status"] == "done"
        assert all(i["status"] == "done" for i in st["steps"].values())
    finally:
        orch.close()


def test_preflight_missing_profile(workspace):
    orch = Orchestrator(workspace, on_event=lambda m: None)
    manifest = yaml.safe_load((workspace / "episode.manifest.yaml").read_text(encoding="utf-8"))
    manifest["profile"] = "config/nonexistent_profile.yaml"
    bad_manifest = workspace / "bad_manifest.yaml"
    bad_manifest.write_text(yaml.safe_dump(manifest), encoding="utf-8")

    try:
        with pytest.raises(FileNotFoundError, match="Pre-flight validation failed"):
            orch.run(bad_manifest, dry_run=True)
    finally:
        orch.close()


def test_resume_skips_done_steps(workspace):
    orch = Orchestrator(workspace, on_event=lambda m: None)
    try:
        orch.run(workspace / "episode.manifest.yaml", dry_run=True, until="m2_audio")

        # break m2 artifacts to simulate an interrupted run mid-conveyor
        (workspace / "runs" / "ep-test" / "audio" / "speechplan.json").unlink()
        orch.state.set_step("ep-test", "m2_audio", "failed", error="simulated")

        calls = []
        orig = orch.modules["m1_script"].run
        orch.modules["m1_script"].run = lambda ctx: calls.append("m1") or orig(ctx)

        orch.resume("ep-test", dry_run=True)
        assert "m1" not in calls, "done step must not re-run on resume"
        for rel in EXPECTED_ARTIFACTS:
            assert (workspace / "runs" / "ep-test" / rel).exists()
    finally:
        orch.close()


def test_artifacts_validate_against_contracts(workspace):
    from core.contracts import (AssemblyResult, Metadata, Script, Scenes,
                                SpeechPlan, Subtitles, WorldContext)

    orch = Orchestrator(workspace, on_event=lambda m: None)
    try:
        orch.run(workspace / "episode.manifest.yaml", dry_run=True)
    finally:
        orch.close()

    rd = workspace / "runs" / "ep-test"
    Script(**json.loads((rd / "script" / "script.json").read_text(encoding="utf-8")))
    SpeechPlan(**json.loads((rd / "audio" / "speechplan.json").read_text(encoding="utf-8")))
    Subtitles(**json.loads((rd / "subtitles" / "subtitles.json").read_text(encoding="utf-8")))
    WorldContext(**json.loads((rd / "visual" / "world.json").read_text(encoding="utf-8")))
    Scenes(**json.loads((rd / "visual" / "scenes.json").read_text(encoding="utf-8")))
    AssemblyResult(**json.loads((rd / "video" / "assembly_result.json").read_text(encoding="utf-8")))
    Metadata(**json.loads((rd / "metadata" / "metadata.json").read_text(encoding="utf-8")))
