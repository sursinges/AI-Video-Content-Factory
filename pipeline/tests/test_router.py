"""Router: cache hit, usage accounting, budget stop, retry-on-failure (S0-04)."""

import json

import pytest

from core.providers.router import BudgetExceeded, Provider, ProviderError, Router
from core.state import StateDB


class FlakyProvider(Provider):
    """Fails twice then succeeds — verifies retry policy."""

    adapter = "flaky"

    def __init__(self, **kw):
        super().__init__(**kw)
        self.calls = 0

    def execute(self, payload):
        self.calls += 1
        if self.calls < 3:
            raise ProviderError("transient")
        return {"text": "ok"}


class CostlyProvider(Provider):
    adapter = "costly"

    def execute(self, payload):
        return {"text": "expensive"}


@pytest.fixture
def state(tmp_path):
    s = StateDB(tmp_path / "state.db")
    s.create_run("r1", {"run_id": "r1"})
    yield s
    s.close()


def make_router(state, tmp_path, providers_cfg):
    secret = lambda ref: ""  # noqa: E731
    r = Router(providers_cfg, state, "r1", tmp_path / "runs" / "r1")
    r.registry["llm/flaky"] = FlakyProvider(name="flaky", ptype="llm", cfg={"model": "m"}, resolve_secret=secret)
    r.registry["llm/costly"] = CostlyProvider(name="costly", ptype="llm", cfg={"model": "m"}, resolve_secret=secret)
    return r


def base_cfg(**over):
    cfg = {"defaults": {"llm": "flaky"}, "providers": {}, "budget_limit_usd": 0.0}
    cfg.update(over)
    return cfg


def test_retry_then_success(state, tmp_path):
    r = make_router(state, tmp_path, base_cfg())
    res = r.call("llm", {"prompt": "hi"})
    assert res["text"] == "ok"
    assert r.registry["llm/flaky"].calls == 3


def test_cache_hit_skips_execute(state, tmp_path):
    r = make_router(state, tmp_path, base_cfg())
    r.call("llm", {"prompt": "hi"})
    calls_after_first = r.registry["llm/flaky"].calls
    r.call("llm", {"prompt": "hi"})
    assert r.registry["llm/flaky"].calls == calls_after_first  # served from cache


def test_usage_recorded_in_db_and_jsonl(state, tmp_path):
    r = make_router(state, tmp_path, base_cfg())
    r.call("llm", {"prompt": "hi"}, cost_usd=0.0, tokens=10)
    assert state.usage_spent("r1") == 0.0
    j = json.loads((tmp_path / "runs" / "r1" / "usage.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert j["provider"] == "flaky" and j["tokens"] == 10


def test_paid_call_refused_without_budget(state, tmp_path):
    r = make_router(state, tmp_path, base_cfg())
    with pytest.raises(ProviderError):
        r.call("llm", {"prompt": "hi"}, cost_usd=0.5)


def test_budget_stop(state, tmp_path):
    r = make_router(state, tmp_path, base_cfg(budget_limit_usd=0.4))
    r.call("llm", {"prompt": "a"}, cost_usd=0.3)
    with pytest.raises(BudgetExceeded):
        r.call("llm", {"prompt": "b"}, cost_usd=0.3)


def test_fallback_chain(state, tmp_path):
    cfg = base_cfg(defaults={"llm": "missing"}, fallbacks={"llm": ["flaky"]})
    r = make_router(state, tmp_path, cfg)
    assert r.call("llm", {"prompt": "hi"})["text"] == "ok"


def test_fallback_chain_does_not_leak_model_override(state, tmp_path):
    cfg = base_cfg(defaults={"llm": "missing"}, fallbacks={"llm": ["flaky"]})
    r = make_router(state, tmp_path, cfg)
    r.model_overrides = {"llm": "special-override-model"}
    assert r.call("llm", {"prompt": "hi"})["text"] == "ok"
    assert r.registry["llm/flaky"].model == "m"

