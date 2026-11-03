"""Product editions (strategy 'Product Modes'): desktop vs web.

Two editions of one codebase:

- **desktop** (Community Edition) — single-owner local install. No sign-in,
  no tenants, no credits, no run queue; local GPU providers (Stable
  Diffusion, faster-whisper, Chatterbox/Silero/F5) are first-class; UI on
  localhost. Hosted/tenant machinery is structurally OFF.
- **web** (Cloud) — hosted multi-tenant service: sign-in required,
  per-tenant data roots and BYOK, run queue, disk quotas, credits. Local
  GPU models are optional, never assumed.

Resolution order: `PIPELINE_EDITION` env (subprocesses / explicit runs) ->
`config/ui_settings.yaml` `edition:` -> default **desktop**. Arming the web
auth gate additionally requires `hosted_mode: true` (tenants.read_flags).
"""

import os
from pathlib import Path

_EDITIONS = ("desktop", "web")


def current(workspace: str | Path) -> str:
    env = (os.environ.get("PIPELINE_EDITION") or "").strip().lower()
    if env in _EDITIONS:
        return env
    try:
        import yaml

        data = yaml.safe_load(
            (Path(workspace) / "config" / "ui_settings.yaml").read_text(encoding="utf-8")) or {}
        ed = str(data.get("edition", "")).strip().lower()
        if ed in _EDITIONS:
            return ed
    except Exception:  # noqa: BLE001 — missing/broken file = desktop default
        pass
    return "desktop"


def is_web(workspace: str | Path) -> bool:
    return current(workspace) == "web"


def is_desktop(workspace: str | Path) -> bool:
    return current(workspace) == "desktop"
