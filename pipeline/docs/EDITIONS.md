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

Planned (not implemented — do not advertise as ready): usage-based managed
compute, production-pack marketplace.

## Hybrid Workers (Phase-1 prototype — Experimental)

The Web edition can route GPU-heavy episodes to customer-owned machines:
the control plane queues runs, workers claim them, execute the pipeline
locally with their own BYOK keys and model weights, and upload the
artifacts back. Design, lifecycle, security model and validation gates:
[`docs/RFC_HYBRID_WORKERS.md`](RFC_HYBRID_WORKERS.md).

Enable (control plane):

```yaml
# config/ui_settings.yaml
workers_enabled: true
```
```bash
# .env on the control plane
WORKER_TOKEN=<long-random-secret>
```

Run a worker (customer machine, full pipeline checkout):

```bash
python tools/worker_agent.py --server https://cloud.example.com \
    --token <WORKER_TOKEN> --worker-id my-rig
```

This is a Phase-1 prototype (single worker, poll-based claim, host-scoped
artifact upload) — mark it experimental in any public material until the
two-machine validation from the RFC passes.

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

## Deploying the Web edition

Three supported paths (all run the same code; the edition comes from env/config):

**1. systemd + Caddy (Ubuntu 22.04/24.04, recommended bare-metal path):**

```bash
sudo PIPELINE_DOMAIN=video.example.com bash pipeline/deploy/install.sh /opt/pipeline
```

The installer installs ffmpeg + Python ≥3.11 (deadsnakes on 22.04), clones the
repo, creates a venv (`pip install -e ./pipeline` — CPU deps only), seeds
`config/ui_settings.yaml` with the Web edition, installs the systemd unit
(`deploy/pipeline.service`, sets `PIPELINE_EDITION=web`) and the Caddy site
with auto-HTTPS. Health: `curl http://127.0.0.1:8765/api/health`,
edition: `/api/edition`.

**2. Docker (CPU container, orchestration + cloud providers):**

```bash
docker build -t ai-video-factory .
docker run -p 8765:8765 -v factory-data:/app/pipeline/data \
  -v factory-config:/app/pipeline/config ai-video-factory
```

The container does not include GPU stacks — local models are a Desktop concern.

**3. Any process manager** — the app is a FastAPI/uvicorn service:
`python -c "from ui.server import main; main(port=8765, host='127.0.0.1')"`
behind a reverse proxy, with `PIPELINE_EDITION=web` in the environment.

Packaging note: the wheel (`pip wheel ./pipeline`) carries the code **and**
all runtime data (config/prompts/motion templates/static UI) and imports
cleanly — but the project name `pipeline` is already taken on PyPI, so
distribution today is via git/source installs (the wheel is for internal
packaging/air-gapped installs).

## Implementation map

- `core/edition.py` — edition resolution (env → config → desktop default)
- `core/tenants.py::read_flags` — desktop forces `hosted_mode=False`
- `ui/server.py` — auth-gate middleware, run queue, `/api/edition`
- `ui/api_auth.py` — sessions, credits, admin (`/api/auth/*`)
- `ui/api_worker.py` + `tools/worker_agent.py` — Hybrid Workers Phase-1 (experimental)
- `core/diagnostics.py::check_edition` — `pipeline doctor` reports the edition
- `pipeline/pyproject.toml` — `[desktop]` extra (GPU stack); web needs no extras
- `pipeline/deploy/` — install.sh, systemd unit, Caddy site (Web edition); `Dockerfile` at repo root
