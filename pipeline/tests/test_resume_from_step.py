"""Tests for resuming and re-running from a specific step."""

from pathlib import Path
import pytest
import yaml

from core.orchestrator import Orchestrator


def test_resume_from_step(tmp_path):
    src = Path(__file__).resolve().parent.parent
    (tmp_path / "config").mkdir()
    for f in ("providers.yaml", "channel.profile.yaml"):
        text = (src / "config" / f).read_text(encoding="utf-8")
        if f == "channel.profile.yaml":
            text = text.replace("default_target_minutes: 45", "default_target_minutes: 1")
            text = text.replace("chunk_chars: [6000, 9000]", "chunk_chars: [300, 600]")
        (tmp_path / "config" / f).write_text(text, encoding="utf-8")

    manifest = yaml.safe_load((src / "config" / "episode.template.yaml").read_text(encoding="utf-8"))
    manifest["run_id"] = "ep-step-test"
    manifest_path = tmp_path / "manifest.yaml"
    manifest_path.write_text(yaml.safe_dump(manifest), encoding="utf-8")

    events = []
    orch = Orchestrator(tmp_path, on_event=lambda m: events.append(m))
    try:
        # Run up to m2_audio
        orch.run(manifest_path, until="m2_audio", dry_run=True)
        assert orch.state.is_step_done("ep-step-test", "m1_script")
        assert orch.state.is_step_done("ep-step-test", "m2_audio")
        assert not orch.state.is_step_done("ep-step-test", "m3_visual")

        # Now resume from m2_audio
        orch.resume("ep-step-test", from_step="m2_audio", until="m2_audio", dry_run=True)
        # m1_script was preserved
        assert orch.state.is_step_done("ep-step-test", "m1_script")
        assert orch.state.is_step_done("ep-step-test", "m2_audio")

        # Test invalid step raises ValueError
        with pytest.raises(ValueError, match="unknown step 'invalid_step'"):
            orch.resume("ep-step-test", from_step="invalid_step", dry_run=True)
    finally:
        orch.close()
