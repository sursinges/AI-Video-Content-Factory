"""Contract golden files: valid ones load, broken ones are rejected (S0-02)."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from core.contracts import (AssemblyResult, EpisodeManifest, Metadata, PublishResult,
                            Scene, Scenes, Script, SpeechPlan, Subtitles, WorldContext)

GOLDEN = Path(__file__).parent / "golden"


def golden(name):
    return json.loads((GOLDEN / name).read_text(encoding="utf-8"))


def test_manifest_ok():
    EpisodeManifest(**golden("manifest.json"))


def test_script_ok():
    Script(**golden("script.json"))


def test_speechplan_and_subtitles_ok():
    SpeechPlan(**golden("speechplan.json"))
    Subtitles(**golden("subtitles.json"))


def test_world_and_scenes_ok():
    WorldContext(**golden("world.json"))
    Scenes(**golden("scenes.json"))


def test_assembly_metadata_publish_ok():
    AssemblyResult(**golden("assembly.json"))
    Metadata(**golden("metadata.json"))
    PublishResult(**golden("publish.json"))


# -- rejections --------------------------------------------------------------

def test_script_rejects_wrong_char_count():
    s = golden("script.json")
    s["full_text_char_count"] += 1
    with pytest.raises(ValidationError):
        Script(**s)


def test_script_rejects_wrong_roles():
    s = golden("script.json")
    s["chunks"][0]["role"] = "body"
    with pytest.raises(ValidationError):
        Script(**s)


def test_manifest_allows_free_length():
    m = golden("manifest.json")
    assert m["target_minutes"] is None  # length is not fixed anywhere


def test_metadata_rejects_long_title():
    m = golden("metadata.json")
    m["title"] = "x" * 71
    with pytest.raises(ValidationError):
        Metadata(**m)


def test_scenes_reject_non_monotonic():
    s = golden("scenes.json")
    s["scenes"][0], s["scenes"][1] = s["scenes"][1], s["scenes"][0]
    with pytest.raises(ValidationError):
        Scenes(**s)


def test_scene_rejects_inverted_time():
    with pytest.raises(ValidationError):
        Scene(id="s001", start=10.0, end=5.0, text_ref="x", prompt="p", seed=1)
