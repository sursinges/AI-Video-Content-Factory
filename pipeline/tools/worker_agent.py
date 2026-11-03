#!/usr/bin/env python3
"""Hybrid Workers agent (Phase-1 prototype — docs/RFC_HYBRID_WORKERS.md).

Runs on the customer's machine: claims queued episodes from the control
plane (Web edition), executes the pipeline locally with the worker's own
BYOK keys and model weights, uploads the artifacts back and reports.

Usage (from the pipeline/ directory of a full checkout):
    python tools/worker_agent.py --server https://cloud.example.com \
        --token WORKER_TOKEN [--worker-id my-rig] [--once] [--dry-run]

Requires ffmpeg on PATH and the regular pipeline dependencies; a local GPU
is optional — providers come from this machine's own .env (BYOK stays here).
"""

import argparse
import subprocess
import sys
import threading
import time
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[1]

# artifacts mirrored back to the control plane after a successful run
UPLOAD_ARTIFACTS = [
    "video/episode.mp4",
    "video/assembly_result.json",
    "video/effects_report.json",
    "video/timecodes.json",
    "metadata/metadata.json",
    "metadata/thumbnail.png",
    "subtitles/subtitles.json",
    "subtitles/subtitles.srt",
    "visual/world.json",
    "visual/scenes.json",
    "usage.jsonl",
    "publish_result.json",
]


def http(method: str, url: str, token: str, **kwargs):
    import httpx

    headers = {"Authorization": f"Bearer {token}"}
    return httpx.request(method, url, headers=headers, timeout=120, **kwargs)


def claim(server: str, token: str, worker_id: str) -> dict | None:
    r = http("POST", f"{server}/api/worker/claim", token,
             json={"worker_id": worker_id})
    r.raise_for_status()
    return r.json().get("job")


def heartbeat_loop(server: str, token: str, worker_id: str, run_id: str, stop: threading.Event):
    while not stop.wait(300):  # every 5 min, lease is 30 min
        try:
            http("POST", f"{server}/api/worker/heartbeat", token,
                 json={"run_id": run_id, "worker_id": worker_id}).raise_for_status()
        except Exception as e:  # noqa: BLE001 — heartbeat is best-effort
            print(f"[worker] heartbeat notice: {e}", flush=True)


def execute(run_id: str, manifest_yaml: str, dry_run: bool) -> tuple[bool, str, Path]:
    """Write the manifest and run the pipeline in this worker's workspace."""
    runs_dir = WORKSPACE / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = runs_dir / f"{run_id}.manifest.yaml"
    manifest_path.write_text(manifest_yaml, encoding="utf-8")
    log_path = runs_dir / f"{run_id}.worker.log"
    cmd = [sys.executable, "-u", "-m", "core.cli", "run", str(manifest_path)]
    if dry_run:
        cmd.append("--dry-run")
    with log_path.open("w", encoding="utf-8") as log:
        proc = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT,
                              cwd=str(WORKSPACE))
    return proc.returncode == 0, log_path.read_text(encoding="utf-8")[-4000:], manifest_path


def upload_artifacts(server: str, token: str, run_id: str) -> list[str]:
    uploaded = []
    for rel in UPLOAD_ARTIFACTS:
        p = WORKSPACE / "runs" / run_id / rel
        if not p.exists() or p.stat().st_size == 0:
            continue
        r = http("PUT", f"{server}/api/worker/artifact/{run_id}/{rel}", token,
                 content=p.read_bytes())
        r.raise_for_status()
        uploaded.append(rel)
    return uploaded


def report(server: str, token: str, run_id: str, worker_id: str, status: str, error: str = ""):
    r = http("POST", f"{server}/api/worker/report", token,
             json={"run_id": run_id, "worker_id": worker_id, "status": status, "error": error})
    r.raise_for_status()


def process_one(server: str, token: str, worker_id: str, dry_run: bool) -> bool:
    """Claim -> run -> upload -> report. Returns True if a job was processed."""
    job = claim(server, token, worker_id)
    if not job:
        return False
    run_id, manifest_yaml = job["run_id"], job.get("manifest_yaml") or ""
    print(f"[worker] claimed {run_id}", flush=True)
    stop = threading.Event()
    hb = threading.Thread(target=heartbeat_loop,
                          args=(server, token, worker_id, run_id, stop), daemon=True)
    hb.start()
    try:
        ok, log_tail, _ = execute(run_id, manifest_yaml, dry_run)
        if ok:
            uploaded = upload_artifacts(server, token, run_id)
            print(f"[worker] {run_id}: uploaded {len(uploaded)} artifacts", flush=True)
            report(server, token, run_id, worker_id, "done")
        else:
            report(server, token, run_id, worker_id, "failed", error=log_tail)
    except Exception as e:  # noqa: BLE001 — the agent must always report back
        try:
            report(server, token, run_id, worker_id, "failed", error=str(e)[:4000])
        except Exception:  # noqa: BLE001
            pass
        raise
    finally:
        stop.set()
    return True


def main():
    ap = argparse.ArgumentParser(description="Hybrid Workers agent (experimental)")
    ap.add_argument("--server", required=True, help="control plane base URL, e.g. https://video.example.com")
    ap.add_argument("--token", required=True, help="WORKER_TOKEN set on the control plane")
    ap.add_argument("--worker-id", default=f"{time.strftime('%Y%m%d')}-local")
    ap.add_argument("--poll-sec", type=int, default=10)
    ap.add_argument("--once", action="store_true", help="process at most one job and exit")
    ap.add_argument("--dry-run", action="store_true", help="run episodes with mock providers")
    args = ap.parse_args()

    print(f"[worker] {args.worker_id} -> {args.server} (poll {args.poll_sec}s)", flush=True)
    while True:
        try:
            processed = process_one(args.server, args.token, args.worker_id, args.dry_run)
        except Exception as e:  # noqa: BLE001 — keep polling on transient errors
            print(f"[worker] error: {e}", flush=True)
            processed = False
        if args.once and processed:
            return
        if not processed:
            time.sleep(max(args.poll_sec, 1))


if __name__ == "__main__":
    main()
