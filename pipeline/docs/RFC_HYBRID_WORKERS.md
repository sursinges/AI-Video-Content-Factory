# RFC: Hybrid Workers — control plane + customer-owned GPU workers

**Status:** Phase-1 prototype implemented (`ui/api_worker.py`, `tools/worker_agent.py`) — **Experimental**.
Everything beyond Phase 1 is a design proposal and is not built.
**Related:** `docs/EDITIONS.md` (Web edition), strategy "Hybrid Cloud Strategy"
(cloud manages production, not necessarily rendering).

## 1. Problem

The Web edition runs episodes as local subprocesses on the host. GPU-heavy
work (local SD, faster-whisper, TTS clones) either forces the host to own
GPUs or forces customers onto cloud APIs. Customers (studios, operators)
already own capable machines; they should be able to keep their hardware,
their BYOK keys and their model weights, while the cloud does what it is
good at: projects, queueing, metadata, publishing, collaboration.

Goal: **cloud orchestrates, worker executes.** Never build unlimited GPU
subscriptions; GPU costs stay where the hardware is.

## 2. Non-goals (explicit)

- No managed compute in this RFC (usage-based compute is a later, separate
  decision with its own unit-economics gate).
- No marketplace, no multi-worker scheduling beyond round-robin by claim
  order in Phase 1.
- No cross-machine shared filesystem; artifact sync goes through the API.
- No platform-evasion/proxy features — workers use official APIs.

## 3. Architecture (target)

```
+---------------------------+          +---------------------------+
| Control plane (Web edition) |  HTTPS  | Worker (customer machine) |
| - projects, runs, state.db |<-------->| - full pipeline checkout  |
| - queue (worker_jobs)      |  claim   | - own .env BYOK keys      |
| - run history, UI          |  report  | - local GPU/models        |
| - publish (YouTube OAuth)  |  upload  | - tools/worker_agent.py   |
+---------------------------+          +---------------------------+
```

Split of responsibilities:

| Concern | Control plane | Worker |
|---|---|---|
| Run queue, leases | ✓ | — |
| Manifest authoring, metadata, UI | ✓ | — |
| M1–M6 execution | — | ✓ (local providers) |
| BYOK provider keys | host vault (hosted engines) | worker's own `.env` |
| Model weights | — | worker's `models/` |
| Artifacts (video, subtitles, usage) | stores & serves | uploads |
| Publishing (M6) | ✓ (per-tenant OAuth) | — |

## 4. Job lifecycle

```
user launches episode (Web UI)
  -> runs row: status='queued', worker_jobs row: status='queued'
worker: POST /api/worker/claim            -> 200 {run_id, manifest_yaml} | {job: null}
  runs.status='running', worker_jobs.status='claimed' (lease = 30 min)
worker writes runs/<id>.manifest.yaml locally, runs `pipeline run` (own .env)
worker: PUT /api/worker/artifact/<run_id>/<rel>   (episode.mp4, srt, metadata, usage.jsonl…)
worker: POST /api/worker/heartbeat        -> lease renewed (running subprocess)
worker: POST /api/worker/report {status: done|failed}
  runs.status='done'|'failed', worker_jobs.status='done'|'failed'
```

Failure semantics:

- **Lease expiry** (heartbeat missed): `worker_jobs` rows older than the
  lease return to `queued` and can be re-claimed. The run itself is set
  back to `queued` too. Pipeline checkpoints (`steps` table + artifacts)
  make re-execution cheap — done steps are skipped on the next worker.
- **Worker crash mid-run**: same as lease expiry; `resume` semantics apply.
- **Report failed**: run marked `failed`, error stored; the hosted credit
  refund flow (already implemented for local failures) applies.
- **Idempotent artifact upload**: same rel-path overwrites atomically
  (tmp file + rename on the control plane).

## 5. Security model

- Workers authenticate with a shared `WORKER_TOKEN` (env on the control
  plane; `Authorization: Bearer`). No worker = no worker API (403).
- `/api/worker/*` is exempt from the browser session gate but never from
  the token check.
- Workers never see host provider keys and vice versa: the worker executes
  with its own `.env` (BYOK stays with the hardware that pays for it).
- Artifact paths are validated against `runs/<run_id>/` containment
  (run_id pattern `^[A-Za-z0-9][A-Za-z0-9._-]{0,80}$`, no traversal, size cap).
- Control plane stores artifacts but does not execute anything a worker
  sends; manifests are authored on the control plane only.

## 6. Phase plan

- **Phase 1 (implemented, experimental)** — single worker, DB queue,
  claim/heartbeat/report + artifact upload; agent script
  `tools/worker_agent.py`; enabled only when `workers_enabled: true` in
  `config/ui_settings.yaml` (Web edition). Tests: `tests/test_workers.py`.
- **Phase 2** — live progress: worker streams step transitions into the
  `steps` table; run progress UI works for remote runs as it does locally.
- **Phase 3** — worker pools: worker registration (labels: gpu, vram,
  models), scheduling by label/affinity, per-worker concurrency, admin UI.
- **Phase 4** — metering: worker-reported `usage.jsonl` folded into the
  tenant spend summary; the billing groundwork (`pricing.yaml`,
  `/api/estimate`) prices remote runs like local ones.

## 7. What is deliberately NOT in the prototype

- No WebSockets/push: claim-poll every N seconds is enough for Phase 1.
- No artifact dedup/CDN: control-plane disk under `runs/<id>/` is fine.
- No automatic worker provisioning (that is managed compute, later).
- No encryption at rest beyond what the host already provides.

## 8. Validation before widening (owner gates)

1. Two-machine smoke: control plane on a VPS, worker on the local RTX rig,
   one real episode end-to-end (this machine + any second box).
2. Kill-recovery drill: `SIGKILL` the agent mid-m2, verify re-claim and
   checkpoint resume produce an identical episode.
3. Only after 1–2: consider a small private beta with 1–2 studio partners
   (per the strategy: validate demand before building more).
