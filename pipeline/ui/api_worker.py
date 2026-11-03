"""Hybrid Workers API (Phase-1 prototype, docs/RFC_HYBRID_WORKERS.md).

Customer-owned workers claim queued episodes, execute the pipeline locally
(with their own BYOK keys and model weights) and upload the artifacts back.
Enabled when the control-plane operator sets WORKER_TOKEN in .env; runs are
routed into the worker queue when ui_settings.yaml has workers_enabled: true
(Web edition).

Jobs are enqueued into the state.db of the tenant who launched the run (the
tenant owns the run row, artifacts and billing). The worker API has no
session, so every endpoint locates the job by scanning the host state.db and
all tenant state.db files (same pattern as the run-queue's _running_count),
then re-enters the tenant context for manifest reads and artifact writes.

Endpoints (all require Authorization: Bearer <WORKER_TOKEN>):
  POST /api/worker/claim    {worker_id}            -> {job: {run_id, manifest_yaml}} | {job: null}
  POST /api/worker/heartbeat {run_id, worker_id}   -> renew lease
  POST /api/worker/report   {run_id, worker_id, status, error?}
  PUT  /api/worker/artifact/{run_id}/{rel}          (raw bytes, size-capped)
  GET  /api/worker/jobs                             (debug: queue state across dbs)
"""

import os
import re
from contextlib import contextmanager
from pathlib import Path

from fastapi import Request
from starlette.responses import JSONResponse

import ui.server as srv
from core import tenants
from ui.server import app, data_root, runs_root

_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,80}$")
_MAX_ARTIFACT_BYTES = 2 * 1024 * 1024 * 1024  # 2 GB per artifact


def worker_token() -> str:
    tok = (os.environ.get("WORKER_TOKEN") or "").strip()
    if tok:
        return tok
    envf = Path(srv.WORKSPACE) / ".env"
    if envf.exists():
        for line in envf.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.strip().startswith("WORKER_TOKEN="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def _check_token(request: Request) -> bool:
    tok = worker_token()
    if not tok:
        return False
    auth = request.headers.get("authorization", "")
    return auth == f"Bearer {tok}" or request.headers.get("x-worker-token") == tok


def _deny():
    if not worker_token():
        return JSONResponse({"error": "worker mode disabled (set WORKER_TOKEN on the control plane)"},
                            status_code=403)
    return JSONResponse({"error": "unauthorized worker"}, status_code=401)


def iter_worker_dbs():
    """(tenant_uid | None, StateDB) pairs: host db first, then every tenant db."""
    from core.state import StateDB

    yield None, StateDB(data_root() / "data" / "state.db")
    for d in sorted((Path(srv.WORKSPACE) / "data" / "tenants").glob("*/data/state.db")):
        yield d.parts[-3], StateDB(d)


@contextmanager
def _job_context(run_id: str, worker_id: str | None = None):
    """Find the worker job across host+tenant dbs; yield (db, row, tenant token).
    Re-enters the owning tenant's context so runs_root()/_state() resolve."""
    from core.state import StateDB

    for uid, db in iter_worker_dbs():
        try:
            q = "SELECT * FROM worker_jobs WHERE run_id=?"
            args: list = [run_id]
            if worker_id is not None:
                q += " AND worker_id=?"
                args.append(worker_id)
            row = db.conn.execute(q, args).fetchone()
            if not row:
                continue
            tset = tenants.set_tenant(uid) if uid else None
            try:
                yield db, row, uid
            finally:
                if tset is not None:
                    tenants.reset_tenant(tset)
            return
        finally:
            db.close()
    # nothing found: yield a throwaway global db so callers can 404 cleanly
    db = StateDB(data_root() / "data" / "state.db")
    try:
        yield db, None, None
    finally:
        db.close()


@app.post("/api/worker/claim")
async def api_worker_claim(request: Request):
    if not _check_token(request):
        return _deny()
    body = await request.json() if (request.headers.get("content-type") or "").startswith("application/json") else {}
    worker_id = str((body or {}).get("worker_id") or "worker").strip()[:64]
    for uid, db in iter_worker_dbs():
        try:
            job = db.claim_next_worker_job(worker_id)
            if not job:
                continue
            run_id = job["run_id"]
            tset = tenants.set_tenant(uid) if uid else None
            try:
                mf = runs_root() / f"{run_id}.manifest.yaml"
                manifest_yaml = mf.read_text(encoding="utf-8") if mf.exists() else ""
                return {"job": {"run_id": run_id, "manifest_yaml": manifest_yaml,
                                "tenant": uid}}
            finally:
                if tset is not None:
                    tenants.reset_tenant(tset)
        finally:
            db.close()
    return {"job": None}


@app.post("/api/worker/heartbeat")
async def api_worker_heartbeat(request: Request):
    if not _check_token(request):
        return _deny()
    body = await request.json()
    run_id, worker_id = str(body.get("run_id") or ""), str(body.get("worker_id") or "")
    with _job_context(run_id, worker_id) as (db, row, _uid):
        if row is None:
            return JSONResponse({"error": "job not found"}, status_code=404)
        return {"ok": db.renew_worker_lease(run_id, worker_id)}


@app.post("/api/worker/report")
async def api_worker_report(request: Request):
    if not _check_token(request):
        return _deny()
    body = await request.json()
    run_id, worker_id = str(body.get("run_id") or ""), str(body.get("worker_id") or "")
    status = str(body.get("status") or "")
    if not _RUN_ID_RE.match(run_id) or status not in ("done", "failed"):
        return JSONResponse({"error": "bad run_id or status"}, status_code=400)
    with _job_context(run_id, worker_id) as (db, row, _uid):
        if row is None:
            return JSONResponse({"error": "job not found"}, status_code=404)
        db.finish_worker_job(run_id, worker_id, status, str(body.get("error") or "") or None)
        db.set_run_status(run_id, status)
        return {"ok": True}


@app.put("/api/worker/artifact/{run_id}/{rel:path}")
async def api_worker_artifact(run_id: str, rel: str, request: Request):
    if not _check_token(request):
        return _deny()
    if not _RUN_ID_RE.match(run_id) or not rel:
        return JSONResponse({"error": "bad run_id or path"}, status_code=400)
    rel_norm = rel.replace("\\", "/").lstrip("/")
    if ".." in rel_norm.split("/") or rel_norm.startswith("/"):
        return JSONResponse({"error": "path outside run directory"}, status_code=400)
    with _job_context(run_id) as (db, row, _uid):
        if row is None:
            return JSONResponse({"error": "job not found"}, status_code=404)
        rd = runs_root() / run_id
        dest = (rd / rel_norm).resolve()
        if not str(dest).startswith(str(rd.resolve())):
            return JSONResponse({"error": "path outside run directory"}, status_code=400)
        payload = await request.body()
        if len(payload) > _MAX_ARTIFACT_BYTES:
            return JSONResponse({"error": "artifact exceeds size cap"}, status_code=413)
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".part")
        tmp.write_bytes(payload)
        tmp.replace(dest)
        return {"ok": True, "path": f"runs/{run_id}/{rel_norm}"}


@app.get("/api/worker/jobs")
async def api_worker_jobs(request: Request):
    if not _check_token(request):
        return _deny()
    jobs = []
    for uid, db in iter_worker_dbs():
        try:
            for j in db.list_worker_jobs():
                d = dict(j)
                d["tenant"] = uid
                jobs.append(d)
        finally:
            db.close()
    return {"jobs": jobs}
