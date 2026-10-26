"""Tests for universal formats and example manifests."""

from pathlib import Path
import yaml
from core.contracts import EpisodeManifest


def test_formats_definitions():
    workspace = Path(__file__).resolve().parent.parent
    fmt_file = workspace / "config" / "formats.yaml"
    assert fmt_file.exists()
    fmts = yaml.safe_load(fmt_file.read_text(encoding="utf-8"))
    assert isinstance(fmts, dict)

    expected = ["sleep_history", "talking_head", "explainer", "short_vertical", "tech_review", "educational_narrative"]
    for key in expected:
        assert key in fmts, f"Format {key} missing from formats.yaml"
        f = fmts[key]
        assert "name" in f
        assert "tts_speed" in f
        assert "scene_change_seconds" in f


def test_example_manifests():
    root = Path(__file__).resolve().parent.parent.parent
    examples_dir = root / "examples"
    assert examples_dir.exists()

    yaml_files = list(examples_dir.glob("*.yaml"))
    assert len(yaml_files) >= 3

    for yf in yaml_files:
        raw = yaml.safe_load(yf.read_text(encoding="utf-8"))
        manifest = EpisodeManifest(**raw)
        assert manifest.run_id
        assert manifest.topic
        assert manifest.format in [
            "sleep_history", "talking_head", "explainer",
            "short_vertical", "tech_review", "educational_narrative"
        ]
