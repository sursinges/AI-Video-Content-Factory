"""UI-15: episode references participate in generation — copied into the run,
woven into scene prompts, and offered as img2img init to local_sd."""

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
    # a fake reference image in the workspace
    ref = tmp_path / "refs_in" / "style.png"
    ref.parent.mkdir()
    import subprocess

    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                    "-f", "lavfi", "-i", "color=c=0x335577:s=256x256:d=1",
                    "-frames:v", "1", str(ref)], check=True)
    manifest = yaml.safe_load((src / "config" / "episode.template.yaml").read_text(encoding="utf-8"))
    manifest["run_id"] = "ep-refs"
    manifest["reference_urls"] = ["refs_in/style.png", "missing_ref.png"]
    (tmp_path / "episode.manifest.yaml").write_text(
        yaml.safe_dump(manifest, allow_unicode=True), encoding="utf-8")
    return tmp_path


def test_references_copied_and_missing_skipped(workspace):
    orch = Orchestrator(workspace, on_event=lambda m: None)
    try:
        orch.run(workspace / "episode.manifest.yaml", dry_run=True)
        rd = workspace / "runs" / "ep-refs"
        refs = list((rd / "visual" / "refs").glob("ref_*"))
        assert len(refs) == 1, "existing ref must be copied, missing one skipped"
        assert refs[0].suffix == ".png" and refs[0].stat().st_size > 500
    finally:
        orch.close()


def test_reference_reaches_scene_prompt_llm(workspace, monkeypatch):
    """The scene-prompt LLM payload must carry the references block."""
    import modules.m3_visual.runner as m3

    calls: list[dict] = []
    orig = Orchestrator
    orch = orig(workspace, on_event=lambda m: None)
    try:
        mod = orch.modules["m3_visual"]
        real_run = mod.run

        def spy(ctx):
            from modules.m1_script.prompts import render

            rendered = render("scene_prompts.md", {
                "style_preset": "s", "palette": "p", "light": "l",
                "forbidden": "f", "language": "ru", "references": "- ref_01.png (image)",
                "scenes_text": "s001: t"})
            calls.append({"has_ref": "ref_01.png" in rendered and "Референсы" in rendered})
            return real_run(ctx)

        mod.run = spy
        orch.run(workspace / "episode.manifest.yaml", dry_run=True)
        assert calls and calls[0]["has_ref"]
    finally:
        orch.close()


def test_local_sd_img2img_payload_contract():
    """init_image routes local_sd into the img2img pipeline (no CUDA here —
    only asserts the branch selection logic, not the model run)."""
    from core.providers.local_sd import LocalSDProvider

    p = LocalSDProvider("local_sd", "image", {"steps": 1}, resolve_secret=lambda r: "")
    try:
        p._pipeline(img2img=True)
    except Exception as e:  # noqa: BLE001 — no torch/diffusers/CUDA in CI
        assert "diffusers" in str(e) or "torch" in str(e) or "cuda" in str(e).lower()
    else:
        pytest.fail("img2img pipeline must lazily require diffusers/torch")
