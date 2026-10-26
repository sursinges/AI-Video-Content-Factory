# Developer Recipes: Extending the Video Factory

Standard recipes for adding providers, custom modules, prompts, and schema contracts.

---

## 1. Adding a Provider (BYOK API)

### Via Configuration (No Code Required)
Any OpenAI-compatible service (official OpenAI, OpenRouter, Groq, local Ollama, vLLM) connects directly via YAML:

```yaml
# config/providers.yaml -> providers:
  my_custom_llm:
    type: llm                    # llm | tts | stt | image | music | search | publish
    adapter: openai_compatible
    base_url: https://api.example.com/v1
    model: custom-model-id
    api_key_ref: MY_API_KEY      # Environment variable name, NEVER hardcode raw keys
```

Set it as default in `defaults: {llm: my_custom_llm}` or add it to fallback chains in `fallbacks:`.

### Custom Protocol Adapter
For services requiring proprietary SDKs or custom protocols:
1. Create `core/providers/<name>.py` subclassing `Provider` with method `execute(payload) -> dict`.
2. Register the adapter in `adapters` dictionary in `core/providers/router.py:build_registry`.
3. Support `cfg.get("proxy")` for network calls if proxy routing is required.
4. Add unit test with `httpx.MockTransport` in `tests/test_<name>.py`.

---

## 2. Implementing a Pipeline Module

1. Place module execution logic in `modules/<step_name>/runner.py` (class `Module`, `run(ctx) -> list[Artifact]`).
2. Route all model calls exclusively through `ctx.router.call(ptype, payload)`.
3. Save artifacts using `ctx.artifact_path(rel)` and return `(rel, pydantic_instance)`.
4. Ensure all inputs and outputs strictly validate against Pydantic models in `core/contracts/`.
5. Verify dry-run passes: `python -m core.cli run <manifest> --dry-run`.

---

## 3. Adding or Modifying Prompts

Prompts reside in `prompts/`.
- Use string templates with `$var` syntax.
- Variables are dynamically resolved from `manifest` and `channel.profile.yaml`.
- Content language is always controlled by the episode profile, keeping prompts reusable across languages.

---

## 4. Modifying Data Contracts (JSON Schemas)

1. Modify Pydantic model definitions in `core/contracts/*.py`.
2. Update corresponding golden test fixtures in `tests/golden/`.
3. Verify backwards compatibility for existing SQLite runs in `state.db`.
4. Run full test suite: `pytest`.

---

## 5. Verification Commands

```bash
# Run full automated test suite
pytest

# Execute end-to-end dry-run with mock providers
python -m core.cli run episode.manifest.yaml --dry-run

# Run full system diagnostics
python -m core.cli doctor

# Check run history
python -m core.cli status
```
