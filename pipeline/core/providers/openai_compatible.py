"""Universal adapter: any OpenAI-compatible endpoint (base_url + key + model).
Covers official APIs, resellers, gateways and local servers (Ollama, LM Studio)
without writing code — architecture §3.3."""

import httpx

from core.providers.router import Provider, ProviderError


class OpenAICompatibleProvider(Provider):
    adapter = "openai_compatible"

    def execute(self, payload: dict) -> dict:
        base_url = self.cfg.get("base_url", "").rstrip("/")
        if not base_url:
            raise ProviderError(f"provider '{self.name}': base_url is not configured")
        model = self.model
        if "openrouter.ai" in base_url and model == "glm-5.2:free":
            model = "z-ai/glm-5.2:free"
        body = {
            "model": model,
            "messages": [{"role": "user", "content": payload["prompt"]}],
        }
        if payload.get("system"):
            body["messages"].insert(0, {"role": "system", "content": payload["system"]})
        for k in ("temperature", "max_tokens"):
            if payload.get(k) is not None:
                body[k] = payload[k]

        try:
            # cfg["_transport"] is a test seam (httpx.MockTransport); YAML never sets it.
            # cfg["proxy"] routes the call through a proxy (per-provider, M6 privacy).
            proxy = self.cfg.get("proxy")
            client_kwargs = {"transport": self.cfg.get("_transport")} if self.cfg.get("_transport") \
                else {"proxy": proxy} if proxy else {}
            secret = (self.secret() or "").strip()
            headers = {}
            if secret:
                headers["Authorization"] = f"Bearer {secret}"
            elif self.cfg.get("api_key_ref"):
                raise ProviderError(
                    f"provider '{self.name}': API key '{self.cfg.get('api_key_ref')}' is not set in environment or .env"
                )
            if "openrouter.ai" in base_url:
                headers["HTTP-Referer"] = self.cfg.get("referer", "http://localhost:8765")
                headers["X-Title"] = self.cfg.get("app_title", "Pipeline")
            with httpx.Client(timeout=self.cfg.get("timeout_sec", 120), **client_kwargs) as client:
                resp = client.post(
                    f"{base_url}/chat/completions",
                    headers=headers,
                    json=body,
                    timeout=self.cfg.get("timeout_sec", 120),
                )
        except httpx.HTTPError as e:
            raise ProviderError(f"provider '{self.name}': network error: {e}") from e
        if resp.status_code == 429:
            err = ProviderError(f"provider '{self.name}': rate limited")
            err.headers = resp.headers  # router honors Retry-After
            raise err
        if resp.status_code >= 400:
            raise ProviderError(f"provider '{self.name}': HTTP {resp.status_code}: {resp.text[:300]}")
        data = resp.json()
        try:
            res = {"text": data["choices"][0]["message"]["content"]}
            if "usage" in data and isinstance(data["usage"], dict):
                res["usage"] = data["usage"]
            return res
        except (KeyError, IndexError) as e:
            raise ProviderError(f"provider '{self.name}': unexpected response shape") from e

