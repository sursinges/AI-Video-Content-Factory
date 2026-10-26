"""S1 tests: skeleton + validator (S1-02), chunk chain (S1-03), critic
regeneration loop (S1-04), factcheck (S1-05), dry-run on 3 topics (S1-06)."""

import json
from pathlib import Path

import pytest
import yaml

from core.contracts import Script
from core.orchestrator import Orchestrator
from core.providers.router import Provider, Router
from core.state import StateDB
from modules.m1_script.chunks import mock_text
from modules.m1_script.prompts import extract_json
from modules.m1_script.validator import validate

SKELETON_JSON = json.dumps({
    "description": "Тестовый скелет",
    "anchors": [f"якорь {i}" for i in range(1, 11)],
    "chunks_with_examples": [2],
    "forms": [f"форма {i}" for i in range(1, 9)],
    "ideas": ["единственная идея основного блока"],
    "forbidden_phrases": ["в современном мире"],
    "self_instructions": ["держать плотность"],
    "number_of_parts": 3,
    "body_parts_count": 1,
}, ensure_ascii=False)


class ScriptedProvider(Provider):
    """Returns queued responses; records prompt snippets for assertions."""

    adapter = "scripted"

    def __init__(self, responses: list[str]):
        super().__init__(name="fake", ptype="llm", cfg={"model": "fake"}, resolve_secret=lambda r: "")
        self.responses = list(responses)
        self.prompts: list[str] = []

    def execute(self, payload):
        self.prompts.append(payload["prompt"])
        return {"text": self.responses.pop(0) if self.responses else "{}"}


@pytest.fixture
def workspace(tmp_path):
    src = Path(__file__).resolve().parent.parent
    (tmp_path / "config").mkdir()
    for f in ("providers.yaml", "channel.profile.yaml"):
        (tmp_path / "config" / f).write_text((src / "config" / f).read_text(encoding="utf-8"), encoding="utf-8")
    return tmp_path


def make_ctx(workspace, topic, dry_run=False, scripted: ScriptedProvider | None = None):
    profile = yaml.safe_load((workspace / "config" / "channel.profile.yaml").read_text(encoding="utf-8"))
    profile.setdefault("script", {})["default_target_minutes"] = 7  # -> 3 parts, 1 body idea
    from core.contracts import EpisodeManifest
    from modules.base import RunContext

    state = StateDB(workspace / "data" / "state.db")
    state.create_run("t", {"run_id": "t"})
    cfg = {"defaults": {"llm": "fake"}, "budget_limit_usd": 0.0, "providers": {}}
    router = Router(cfg, state, "t", workspace / "runs" / "t")
    if scripted:
        router.registry["llm/fake"] = scripted
    manifest = EpisodeManifest(run_id="t", channel_id="c", topic=topic)
    run_dir = workspace / "runs" / "t"
    run_dir.mkdir(parents=True, exist_ok=True)
    return RunContext(manifest=manifest, run_dir=run_dir, workspace=workspace, profile=profile,
                      router=router, state=state, library=None, dry_run=dry_run)


# --- S1-02: machine validator ------------------------------------------------

def _ok_text(role):
    profile = {"name": "Мой канал", "final_phrase": "Спокойной ночи.", "address": "ты",
               "script": {"greeting_formula": "Привет. Ты на канале $channel_name"}}
    ctx = type("C", (), {"profile": profile})()
    return mock_text(ctx, role, part=1, min_chars=6000)


def test_validator_passes_compliant_mock_text():
    from modules.m1_script.vars import part_role

    for part, role in ((1, "intro"), (2, "body"), (3, "final")):
        issues = validate(_ok_text(role), role=role, form=part, prev_form=None,
                          min_chars=6000, max_chars=9000, stop_words=["суета"],
                          forbidden_phrases=[], final_phrase="Спокойной ночи.",
                          channel_name="Мой канал", address="ты")
        assert issues == [], f"{role}: {issues}"


def test_validator_catches_violations():
    issues = validate("Это **жирный** текст с двоеточием: плохо. " * 90, role="body", form=2,
                      prev_form=2, min_chars=6000, max_chars=9000, stop_words=[],
                      forbidden_phrases=[], final_phrase="Спокойной ночи.",
                      channel_name="Мой канал", address="ты")
    assert any("разметка" in i for i in issues)
    assert any("двоеточия" in i for i in issues)
    assert any("повтор предложений" in i for i in issues)
    assert any("форма чанка 2 повторяется" in i for i in issues)


def test_validator_final_phrase():
    short_final = "Текст." + " Ещё текст в финале." * 200
    issues = validate(short_final, role="final", form=8, prev_form=None,
                      min_chars=6000, max_chars=9000, stop_words=[],
                      forbidden_phrases=[], final_phrase="Спокойной ночи.",
                      channel_name="Мой канал", address="ты")
    assert any("заканчиваться строкой" in i for i in issues)


def _texts(workspace):
    """Distinct compliant mock texts (part number embedded to avoid router
    cache collisions between identical prompts). Chunk size from the same
    7-min profile override make_ctx uses."""
    profile = yaml.safe_load((workspace / "config" / "channel.profile.yaml").read_text(encoding="utf-8"))
    profile.setdefault("script", {})["default_target_minutes"] = 7
    ctx = type("C", (), {"profile": profile})()
    from core.contracts import EpisodeManifest
    from modules.m1_script.skeleton import compute_parts

    m = EpisodeManifest(run_id="t", channel_id="c", topic="тема проверки")
    _, _, min_c, _ = compute_parts(m, profile)
    return [mock_text(ctx, "intro", part=1, min_chars=min_c),
            mock_text(ctx, "body", part=2, min_chars=min_c),
            mock_text(ctx, "final", part=3, min_chars=min_c)]


def test_validator_passes_compliant_mock_text():
    from modules.m1_script.vars import part_role

    for part, role in ((1, "intro"), (2, "body"), (3, "final")):
        issues = validate(_ok_text(role), role=role, form=part, prev_form=None,
                          min_chars=6000, max_chars=9000, stop_words=["суета"],
                          forbidden_phrases=[], final_phrase="Спокойной ночи.",
                          channel_name="Мой канал", address="ты")
        assert issues == [], f"{role}: {issues}"


def test_validator_catches_violations():
    issues = validate("Это **жирный** текст с двоеточием: плохо. " * 90, role="body", form=2,
                      prev_form=2, min_chars=6000, max_chars=9000, stop_words=[],
                      forbidden_phrases=[], final_phrase="Спокойной ночи.",
                      channel_name="Мой канал", address="ты")
    assert any("разметка" in i for i in issues)
    assert any("двоеточия" in i for i in issues)
    assert any("повтор предложений" in i for i in issues)
    assert any("форма чанка 2 повторяется" in i for i in issues)


def test_validator_final_phrase():
    short_final = "Текст." + " Ещё текст в финале." * 200
    issues = validate(short_final, role="final", form=8, prev_form=None,
                      min_chars=6000, max_chars=9000, stop_words=[],
                      forbidden_phrases=[], final_phrase="Спокойной ночи.",
                      channel_name="Мой канал", address="ты")
    assert any("заканчиваться строкой" in i for i in issues)


def _texts(workspace, part=None, role=None):
    """Distinct compliant mock texts (part number embedded to avoid router
    cache collisions between identical prompts)."""
    profile = yaml.safe_load((workspace / "config" / "channel.profile.yaml").read_text(encoding="utf-8"))
    profile.setdefault("script", {})["default_target_minutes"] = 7
    ctx = type("C", (), {"profile": profile})()
    from modules.m1_script.skeleton import compute_parts

    _, _, min_c, _ = compute_parts(
        type("M", (), {"target_minutes": 7}).__class__ and
        __import__("core.contracts", fromlist=["EpisodeManifest"]).EpisodeManifest(
            run_id="t", channel_id="c", topic="тема проверки"), profile)
    return [mock_text(ctx, "intro", part=1, min_chars=min_c),
            mock_text(ctx, "body", part=2, min_chars=min_c),
            mock_text(ctx, "final", part=3, min_chars=min_c)]


# --- S1-03/S1-04: chunk chain + critic regeneration loop ----------------------

def test_critic_loop_regenerates_chunk(workspace):
    c1, c2, c3 = _texts(workspace)
    c1_fixed = c1 + " Доработанная вступительная часть с усиленным первым абзацем."
    scripted = ScriptedProvider([
        SKELETON_JSON,                                        # skeleton
        c1, c2, c3,                                           # draft pass (in part order)
        json.dumps({"pass": False, "issues": ["слабый хук в первом абзаце"],
                    "instruction": "усиль первый абзац"}),    # critic rejects chunk 1
        c1_fixed,                                             # chunk 1 regenerated
        json.dumps({"pass": True, "issues": []}),             # critic accepts chunk 1
        json.dumps({"pass": True, "issues": []}),             # critic chunk 2
        json.dumps({"pass": True, "issues": []}),             # critic chunk 3
        '{"claims": []}', '{"claims": []}', '{"claims": []}',  # factchecks
    ])
    ctx = make_ctx(workspace, "Тема с перегенерацией", scripted=scripted)
    script = Script(**json.loads(dict(ctx_run(ctx))["script/script.json"]))
    assert all(c.critic_pass for c in script.chunks)
    intro_prompts = [p for p in scripted.prompts if "чанк 1" in p.lower()]
    regen_prompts = [p for p in scripted.prompts if "ПРЕДЫДУЩАЯ ПОПЫТКА" in p]
    assert len(intro_prompts) == 2  # first draft + regenerated version of chunk 1
    assert regen_prompts and "слабый хук" in regen_prompts[0], \
        "regeneration prompt must carry the critic's issues"


def ctx_run(ctx):
    from modules.m1_script.runner import M1Script

    artifacts = M1Script().run(ctx)
    return {rel: m.model_dump_json() for rel, m in artifacts}


# --- S1-05: factcheck flagged claims reach script.json ------------------------

def test_factcheck_flagged_claims(workspace):
    c1, c2, c3 = _texts(workspace)
    scripted = ScriptedProvider([
        SKELETON_JSON,
        c1, c2, c3,                                          # draft pass
        '{"pass": true}', '{"pass": true}', '{"pass": true}',  # critics
        '{"claims": [{"text": "спорная дата", "verdict": "well-known"}]}',
        '{"claims": [{"text": "сомнительное событие", "verdict": "flagged", "note": "нужна проверка"}]}',
        '{"claims": []}',
    ])
    ctx = make_ctx(workspace, "Тема с фактчеком", scripted=scripted)
    data = json.loads(dict(ctx_run(ctx))["script/script.json"])
    statuses = [c["factcheck"]["status"] for c in data["chunks"]]
    assert statuses[1] == "warnings"
    assert data["chunks"][1]["factcheck"]["claims"][0]["verdict"] == "flagged"


# --- S1-06: dry-run on three topics -------------------------------------------

@pytest.mark.parametrize("topic", ["Осада Константинополя 1453", "Тайна пиратских карт",
                                   "Строительство Транссиба"])
def test_dry_run_three_topics(workspace, topic):
    orch = Orchestrator(workspace, on_event=lambda m: None)
    try:
        src = Path(__file__).resolve().parent.parent
        manifest = yaml.safe_load((src / "config" / "episode.template.yaml").read_text(encoding="utf-8"))
        manifest["overrides"] = {"script": {"default_target_minutes": 45}}  # full-size chunks
        manifest["run_id"] = f"ep-{abs(hash(topic)) % 1000:03d}"
        manifest["topic"] = topic
        mp = workspace / f"{manifest['run_id']}.yaml"
        mp.write_text(yaml.safe_dump(manifest, allow_unicode=True), encoding="utf-8")
        orch.run(mp, until="m1_script", dry_run=True)
        script = Script(**json.loads(
            (workspace / "runs" / manifest["run_id"] / "script" / "script.json").read_text(encoding="utf-8")))
        assert script.full_text_char_count >= 11 * 4745 * 0.9  # 45-min budget, 11 parts
        assert all(c.critic_pass for c in script.chunks)
        assert script.chunks[0].text.startswith("Привет")
        assert script.chunks[-1].text.rstrip().endswith("Спокойной ночи.")
    finally:
        orch.close()


def test_extract_json_tolerates_prose():
    assert extract_json('болтовня {"pass": true} болтовня') == {"pass": True}
    assert extract_json("нет json") is None
