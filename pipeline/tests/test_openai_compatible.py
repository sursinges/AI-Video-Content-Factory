"""OpenAI-compatible adapter against a fake endpoint (S0-05 acceptance)."""

import httpx
import pytest

from core.providers.openai_compatible import OpenAICompatibleProvider
from core.providers.router import ProviderError, Router
from core.state import StateDB

OK_BODY = {"choices": [{"message": {"content": "привет от фейкового эндпоинта"}}]}


def make_provider(handler, **cfg_extra):
    transport = httpx.MockTransport(handler)
    cfg = {"base_url": "https://fake.example/v1", "model": "test-model",
           "api_key_ref": "FAKE_KEY", "_transport": transport, **cfg_extra}
    return OpenAICompatibleProvider(name="fake", ptype="llm", cfg=cfg, resolve_secret=lambda ref: "k")


def test_successful_completion():
    p = make_provider(lambda req: httpx.Response(200, json=OK_BODY))
    res = p.execute({"prompt": "тест"})
    assert res["text"] == "привет от фейкового эндпоинта"


def test_http_error_raises_provider_error():
    p = make_provider(lambda req: httpx.Response(500, text="boom"))
    with pytest.raises(ProviderError, match="HTTP 500"):
        p.execute({"prompt": "тест"})


def test_rate_limit_carries_retry_after():
    def handler(req):
        return httpx.Response(429, headers={"Retry-After": "0"}, json={})
    p = make_provider(handler)
    with pytest.raises(ProviderError) as ei:
        p.execute({"prompt": "тест"})
    assert getattr(ei.value, "headers", {}).get("retry-after") == "0"


def test_router_uses_configured_fake_endpoint(tmp_path):
    """The whole point of S0-05: a third-party endpoint works via config only."""
    state = StateDB(tmp_path / "state.db")
    state.create_run("r1", {"run_id": "r1"})
    cfg = {
        "defaults": {"llm": "fake"},
        "budget_limit_usd": 0.0,
        "providers": {"fake": {"type": "llm", "adapter": "openai_compatible"}},
    }
    r = Router(cfg, state, "r1", tmp_path / "runs" / "r1")
    r.registry["llm/fake"] = make_provider(lambda req: httpx.Response(200, json=OK_BODY))
    res = r.call("llm", {"prompt": "тест"})
    assert res["text"] == "привет от фейкового эндпоинта"
    state.close()


def test_missing_api_key_raises_provider_error():
    transport = httpx.MockTransport(lambda req: httpx.Response(200, json=OK_BODY))
    cfg = {"base_url": "https://fake.example/v1", "model": "test-model",
           "api_key_ref": "MISSING_KEY", "_transport": transport}
    p = OpenAICompatibleProvider(name="fake", ptype="llm", cfg=cfg, resolve_secret=lambda ref: "")
    with pytest.raises(ProviderError, match="API key 'MISSING_KEY' is not set"):
        p.execute({"prompt": "тест"})

