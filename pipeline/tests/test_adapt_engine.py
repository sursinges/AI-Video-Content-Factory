"""Tests for adapt_engine (fresh take, data rearrangement, volume preservation)."""

from pathlib import Path
from core.adapt_engine import split_text_into_scenes, run_script_adaptation


class DummyRouter:
    def __init__(self, responses: list[str] | None = None):
        self.responses = responses or ["Адаптированный текст сцены. Погружение в атмосферу."]
        self.calls = []

    def call(self, ptype: str, payload: dict) -> dict:
        self.calls.append((ptype, payload))
        idx = len(self.calls) - 1
        resp = self.responses[idx % len(self.responses)]
        return {"text": resp}


def test_split_text_into_scenes_short():
    t = "Короткий текст сценария."
    scenes = split_text_into_scenes(t, 3)
    assert scenes == [t]


def test_split_text_into_scenes_long():
    paragraphs = [f"Параграф номер {i}. Здесь идёт описание событий, деталей и фактов истории.\n\n" for i in range(50)]
    t = "".join(paragraphs)
    assert len(t) > 3000
    scenes = split_text_into_scenes(t, 3)
    assert len(scenes) == 3
    for s in scenes:
        assert len(s) > 500


def test_run_script_adaptation_single_pass(tmp_path: Path):
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir(parents=True)
    adapt_prompt = prompts_dir / "adapt_script.md"
    adapt_prompt.write_text("Hello $channel_name $source_chars $final_phrase $source_text", encoding="utf-8")

    router = DummyRouter(["Адаптированный атмосферный текст. Спокойной ночи."])
    res = run_script_adaptation(
        source_text="Исходный текст на пару абзацев.",
        profile={"name": "Ночной Канал", "final_phrase": "Спокойной ночи."},
        router=router,
        workspace=tmp_path,
        target_minutes=5,
    )
    assert res["ok"] is True
    assert "Спокойной ночи." in res["script"]
    assert res["scenes_count"] == 1
    assert len(router.calls) == 1
    # Check max_tokens passed
    assert router.calls[0][1].get("max_tokens") == 4096


def test_run_script_adaptation_multi_scene(tmp_path: Path):
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir(parents=True)
    (prompts_dir / "adapt_blueprint.md").write_text("Blueprint: $parts_count $channel_name", encoding="utf-8")
    (prompts_dir / "adapt_scene.md").write_text("Scene: $part_num $parts_count $min_chars $final_instruction", encoding="utf-8")

    long_text = "Длинная история о таинственных событиях древнего мира. " * 200
    assert len(long_text) > 6000

    router = DummyRouter([
        "План: Часть 1 - Загадка, Часть 2 - Кульминация",
        "Текст первой сцены в стиле канала.",
        "Текст второй сцены в стиле канала. Спокойной ночи."
    ])

    res = run_script_adaptation(
        source_text=long_text,
        profile={"name": "Ночной Канал", "final_phrase": "Спокойной ночи."},
        router=router,
        workspace=tmp_path,
    )
    assert res["ok"] is True
    assert res["scenes_count"] >= 2
    assert "Спокойной ночи." in res["script"]
    # 1 blueprint call + N scene calls
    assert len(router.calls) >= 3
