# Editions: Desktop (Community) & Web (Cloud)

One codebase, two editions. The edition changes **what machinery is armed**,
not the production pipeline itself — M1–M6, contracts, providers, formats and
the Web Studio UI are identical in both.

## Feature matrix

| Capability | Desktop (Community) | Web (Cloud) |
|---|---|---|
| License | MIT | MIT (core) |
| Users | single owner | multi-tenant (sign-in required) |
| Auth gate / sessions | — off | on (`hosted_mode`) |
| Per-tenant data roots & BYOK | — | on (tenant `.env`, own `providers.yaml`) |
| Credits / billing | — | on (spend per run, auto-refund on failure) |
| Run queue & concurrency limit | — | on (`max_concurrent_runs`) |
| Disk quotas | — | on (`max_tenant_disk_mb`) |
| Full pipeline M1–M6 | ✓ | ✓ |
| Web Studio UI (10 languages) | ✓ | ✓ |
| CLI (`doctor/run/status/resume/ui`) | ✓ | ✓ |
| MCP server (agent control) | ✓ | ✓ |
| Local GPU providers (SD, faster-whisper, Chatterbox/Silero/F5) | first-class (`pip install pipeline[desktop]`) | optional, never assumed |
| Cloud/API providers (OpenRouter, ElevenLabs, fal.ai…) | ✓ (BYOK) | ✓ (BYOK or host keys) |
| Deployment | `pipeline ui` on localhost | uvicorn/systemd+Caddy (`pipeline/deploy/`) |
| Watched folder, ZIP export, cover studio, image→video | ✓ | ✓ |

Planned (not implemented — do not advertise as ready): Hybrid Cloud control
plane with customer-owned GPU workers, usage-based managed compute,
production-pack marketplace.

## Choosing an edition

The edition is read (in order of priority) from:

1. `PIPELINE_EDITION` env var (`desktop` | `web`) — for subprocesses/CI;
2. `config/ui_settings.yaml` key `edition:`;
3. default: **desktop**.

### Desktop (Community Edition)

```bash
pip install pipeline[desktop]   # local GPU stack (torch, diffusers, whisper)
pipeline ui                     # localhost:8765, no sign-in, full pipeline
```

In desktop the hosted machinery is **structurally off**: even if
`ui_settings.yaml` contains `hosted_mode: true`, it is ignored — no auth
gate, no tenants, no credits, no queue. `pipeline doctor` shows
`edition=desktop, hosted_mode=False`.

### Web (Cloud)

```yaml
# config/ui_settings.yaml (local, not committed)
edition: web
hosted_mode: true          # arms the sign-in gate
registration_open: true    # allow self-registration
max_concurrent_runs: 2     # host-wide run queue
max_tenant_disk_mb: 10240  # per-tenant quota
```

First registered user becomes the host admin (unlimited). Tenants get
isolated `runs/`/data, their own provider keys and per-tenant YouTube OAuth.
Legal docs: fill `pipeline/notes/legal/{terms,privacy}.md` before going live.

## Implementation map

- `core/edition.py` — edition resolution (env → config → desktop default)
- `core/tenants.py::read_flags` — desktop forces `hosted_mode=False`
- `ui/server.py` — auth-gate middleware, run queue, `/api/edition`
- `ui/api_auth.py` — sessions, credits, admin (`/api/auth/*`)
- `core/diagnostics.py::check_edition` — `pipeline doctor` reports the edition
- `pipeline/pyproject.toml` — `[desktop]` extra (GPU stack); web needs no extras
