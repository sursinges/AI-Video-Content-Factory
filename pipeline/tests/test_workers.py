"""Hybrid Workers Phase-1 (docs/RFC_HYBRID_WORKERS.md): durable worker queue,
token-authed claim/heartbeat/report/artifact endpoints, worker routing flag.

Runs the whole cycle through the real app against a temporary workspace:
launch (web edition + workers_enabled) -> queued -> claim -> artifact upload
-> report done, plus lease-expiry requeue and token security. Jobs live in
the launching tenant's state.db; the worker API locates them by scanning
host + tenant dbs (same pattern as the run queue)."""

import pytest
import yaml
from fastapi.testclient import TestClient

import ui.server as srv
from ui.server import app

TOKEN = "wt-test-secret"


@pytest.fixture()
def worker_ws(tmp_path, monkeypatch):
    (tmp_path / "config").mkdir()
    (tmp_path / "data").mkdir()
    (tmp_path / "config" / "ui_settings.yaml").write_text(yaml.safe_dump({
        "edition": "web", "hosted_mode": True, "registration_open": True,
        "workers_enabled": True,
    }), encoding="utf-8")
    (tmp_path / "config" / "providers.yaml").write_text(
        "defaults:\n  llm: mock\n", encoding="utf-8")
    monkeypatch.setattr(srv, "WORKSPACE", tmp_path)
    monkeypatch.setenv("WORKER_TOKEN", TOKEN)
    import ui.api_auth as _auth
    monkeypatch.setattr(_auth, "AUTH_MAX", 1000)
    return tmp_path


def _register_owner() -> TestClient:
    c = TestClient(app)
    r = c.post("/api/auth/register", json={"accepted_terms": True,
                                           "email": "host@test.io", "password": "secret1"})
    assert r.status_code == 200
    return c


def _auth_headers(**extra):
    return {"Authorization": f"Bearer {TOKEN}", **extra}


def _expire_lease(worker_ws, run_id: str):
    """Directly expire the job's lease wherever it lives (host or tenant db)."""
    import sqlite3

    candidates = [worker_ws / "data" / "state.db",
                  *sorted((worker_ws / "data" / "tenants").glob("*/data/state.db"))]
    for db_path in candidates:
        if not db_path.exists():
            continue
        conn = sqlite3.connect(db_path)
        cur = conn.execute("UPDATE worker_jobs SET lease_expires_at=datetime('now','-1 minute') "
                           "WHERE run_id=?", (run_id,))
        conn.commit()
        conn.close()
        if cur.rowcount:
            return
    raise AssertionError(f"worker job {run_id} not found in any state.db")


def test_worker_mode_disabled_without_token(worker_ws, monkeypatch):
    monkeypatch.delenv("WORKER_TOKEN")
    r = TestClient(app).post("/api/worker/claim", json={"worker_id": "w"})
    assert r.status_code == 403


def test_worker_endpoints_require_token(worker_ws):
    r = TestClient(app).post("/api/worker/claim", json={"worker_id": "w"})
    assert r.status_code == 401
    r = TestClient(app).put("/api/worker/artifact/ep-0001/video/episode.mp4", content=b"x")
    assert r.status_code == 401


def test_launch_routes_into_worker_queue(worker_ws):
    c = _register_owner()
    r = c.post("/api/episode", json={"topic": "Worker queue test", "target_minutes": 1})
    assert r.status_code == 200
    assert r.json().get("worker") is True and r.json().get("queued") is True
    jobs = TestClient(app).get("/api/worker/jobs", headers=_auth_headers()).json()["jobs"]
    assert len(jobs) == 1 and jobs[0]["status"] == "queued"
    assert jobs[0]["tenant"], "the job belongs to the launching tenant"


def test_full_claim_upload_report_cycle(worker_ws):
    c = _register_owner()
    r = c.post("/api/episode", json={"topic": "End to end worker", "target_minutes": 1})
    run_id = r.json()["run_id"]

    # two claimers: only one gets the job, the other gets null
    cl = TestClient(app)
    first = cl.post("/api/worker/claim", json={"worker_id": "rig-1"},
                    headers=_auth_headers()).json()
    assert first["job"]["run_id"] == run_id
    assert first["job"]["manifest_yaml"].strip(), "manifest yaml must be returned"
    second = cl.post("/api/worker/claim", json={"worker_id": "rig-2"},
                     headers=_auth_headers()).json()
    assert second["job"] is None

    # heartbeat keeps the lease
    hb = cl.post("/api/worker/heartbeat", json={"run_id": run_id, "worker_id": "rig-1"},
                 headers=_auth_headers())
    assert hb.json()["ok"] is True

    # artifact upload lands inside the tenant's run dir
    art = cl.put(f"/api/worker/artifact/{run_id}/video/episode.mp4",
                 content=b"fake-mp4-bytes", headers=_auth_headers())
    assert art.status_code == 200
    tenant_dirs = list((worker_ws / "data" / "tenants").glob(f"*/runs/{run_id}/video/episode.mp4"))
    assert tenant_dirs and tenant_dirs[0].read_bytes() == b"fake-mp4-bytes"

    # traversal is rejected
    bad = cl.put(f"/api/worker/artifact/{run_id}/../escape.txt",
                 content=b"x", headers=_auth_headers())
    assert bad.status_code == 400

    # report done -> run done, job done
    rep = cl.post("/api/worker/report", json={
        "run_id": run_id, "worker_id": "rig-1", "status": "done"}, headers=_auth_headers())
    assert rep.json()["ok"] is True
    jobs = cl.get("/api/worker/jobs", headers=_auth_headers()).json()["jobs"]
    assert len(jobs) == 1 and jobs[0]["status"] == "done" and jobs[0]["worker_id"] == "rig-1"


def test_expired_lease_is_requeued(worker_ws):
    c = _register_owner()
    run_id = c.post("/api/episode", json={"topic": "Lease expiry", "target_minutes": 1}).json()["run_id"]
    cl = TestClient(app)
    first = cl.post("/api/worker/claim", json={"worker_id": "rig-1"}, headers=_auth_headers()).json()
    assert first["job"]["run_id"] == run_id

    # expire the lease directly, then a new claimer takes the job over
    _expire_lease(worker_ws, run_id)
    second = cl.post("/api/worker/claim", json={"worker_id": "rig-2"}, headers=_auth_headers()).json()
    assert second["job"]["run_id"] == run_id


def test_report_rejects_bad_status(worker_ws):
    cl = TestClient(app)
    r = cl.post("/api/worker/report", json={"run_id": "ep-0001", "worker_id": "w",
                                            "status": "weird"}, headers=_auth_headers())
    assert r.status_code == 400


def test_worker_agent_artifact_manifest():
    """The agent's upload list covers the artifacts the UI depends on."""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
    import worker_agent

    for required in ("video/episode.mp4", "metadata/metadata.json", "usage.jsonl"):
        assert required in worker_agent.UPLOAD_ARTIFACTS
