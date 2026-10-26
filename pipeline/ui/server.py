"""Unified web UI (FastAPI) — the single control surface of the pipeline.

    pipeline ui        # http://127.0.0.1:8765

Live: dashboard (runs/steps/artifacts), new episode, library, YouTube
transcript tool, settings view. Placeholder cards mark the growth map
(publish, antidetect manager, verticals) — disabled by design for now.
"""

import json
import os
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

import yaml
from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from core import tenants
from core.state import LibraryDB, StateDB

WORKSPACE = Path(__file__).resolve().parents[1]
# venv interpreter: Windows uses Scripts/python.exe, Linux uses bin/python
_venv_py = WORKSPACE / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
PY = _venv_py if _venv_py.exists() else Path(sys.executable)

from core.secrets import load_env
load_env(WORKSPACE / ".env")

app = FastAPI(title="pipeline UI")
_procs: dict[str, subprocess.Popen] = {}
BOOT_ID = uuid.uuid4().hex[:8]  # changes on server restart -> stale tabs reload


@app.middleware("http")
async def _version_header(request, call_next):
    response = await call_next(request)
    response.headers["x-ui-version"] = BOOT_ID
    return response


def _ui_token() -> str:
    """Optional shared-secret for /api/* access (LAN exposure). Set UI_TOKEN in .env."""
    import os

    tok = os.environ.get("UI_TOKEN", "")
    if tok:
        return tok.strip()
    envf = WORKSPACE / ".env"
    if envf.exists():
        for line in envf.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.strip().startswith("UI_TOKEN="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def _backup(p: Path):
    """Keep a one-step .bak next to a config file before overwriting it."""
    if p.exists():
        p.with_suffix(p.suffix + ".bak").write_bytes(p.read_bytes())


_RUN_ID_RE = __import__("re").compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,80}$")


@app.middleware("http")
async def _api_guard(request, call_next):
    """Safety net for all API routes: run_id path containment + optional UI_TOKEN auth."""
    path = request.url.path
    if path.startswith("/api/run/"):
        rid = path.split("/")[3] if len(path.split("/")) > 3 else ""
        if not rid or not _RUN_ID_RE.match(rid):
            return JSONResponse({"error": "invalid run_id"}, status_code=400)
    token = _ui_token()
    if token and path.startswith("/api/"):
        ok = request.query_params.get("token") == token or request.headers.get("x-ui-token") == token
        if not ok:
            return JSONResponse({"error": "unauthorized: provide ?token=... (UI_TOKEN in .env)"}, status_code=401)
    return await call_next(request)


def data_root() -> Path:
    """Tenant-aware data root (runs/, data/, notes/, transcripts/ live here)."""
    return tenants.resolve_data_root(WORKSPACE)


def config_root() -> Path:
    """Tenant-aware config root: tenants get their own providers.yaml /
    channel.profile.yaml / formats / presets (per-tenant BYOK, P5-02)."""
    return tenants.config_root(WORKSPACE)


def load_env_ctx():
    """Load provider keys for the current context (global .env, tenant .env wins)."""
    tenants.load_env_stacked(WORKSPACE)


def runs_root() -> Path:
    return data_root() / "runs"


def _dir_size(p: Path) -> int:
    total = 0
    for root, _dirs, files in __import__("os").walk(p):
        for fn in files:
            try:
                total += __import__("os").path.getsize(__import__("os").path.join(root, fn))
            except OSError:
                pass
    return total


def _tenant_over_quota() -> bool:
    """ui_settings.yaml max_tenant_disk_mb: 0 = off. Checked before launches/uploads."""
    try:
        data = yaml.safe_load(UI_CFG.read_text(encoding="utf-8")) or {}
        limit_mb = float(data.get("max_tenant_disk_mb", 0) or 0)
        if limit_mb <= 0 or not tenants.current_tenant():
            return False
        return _dir_size(tenants.tenant_dir(WORKSPACE)) > limit_mb * 1024 * 1024
    except Exception:  # noqa: BLE001
        return False


def _tenant_env() -> dict:
    """Env for pipeline subprocesses: carries the tenant data root, never leaks
    the UI contextvar (subprocesses resolve everything from the env var)."""
    env = dict(os.environ)
    env.pop("PIPELINE_DATA_ROOT", None)
    if tenants.current_tenant():
        env["PIPELINE_DATA_ROOT"] = str(tenants.tenant_dir(WORKSPACE))
        env["YOUTUBE_TOKENS_DIR"] = str(tenants.tenant_dir(WORKSPACE) / "data" / "tokens")
    return env


def _request_user(request: Request) -> dict | None:
    return getattr(request.state, "tenant_user", None)


# --- run queue (P5-03): hosted launches wait for a free slot ----------------
_run_queue: list[dict] = []
_queue_lock = threading.Lock()


def _max_concurrent() -> int:
    try:
        data = yaml.safe_load(UI_CFG.read_text(encoding="utf-8")) or {}
        return max(1, int(data.get("max_concurrent_runs", 1)))
    except Exception:  # noqa: BLE001
        return 1


def _running_count() -> int:
    """Host-wide running runs: global workspace + every tenant db."""
    n = 0
    try:
        st = _state()
        n += st.conn.execute("SELECT COUNT(*) c FROM runs WHERE status='running'").fetchone()["c"]
        st.close()
    except Exception:  # noqa: BLE001
        pass
    for db in (WORKSPACE / "data" / "tenants").glob("*/data/state.db"):
        try:
            conn = __import__("sqlite3").connect(db)
            n += conn.execute("SELECT COUNT(*) c FROM runs WHERE status='running'").fetchone()["c"]
            conn.close()
        except Exception:  # noqa: BLE001
            pass
    return n


def _try_launch_queued():
    while True:
        with _queue_lock:
            if not _run_queue or _running_count() >= _max_concurrent():
                return
            job = _run_queue.pop(0)
        log = open(job["log_path"], "a", encoding="utf-8")
        proc = subprocess.Popen(job.get("cmd") or [str(PY), "-u", "-m", "core.cli", "run", job["manifest_path"]],
                                stdout=log, stderr=subprocess.STDOUT, cwd=str(WORKSPACE),
                                env=job["env"])
        _procs[job["run_id"]] = proc


def _queue_watcher():
    while True:
        time.sleep(4)
        try:
            _try_launch_queued()
        except Exception:  # noqa: BLE001 — the watcher must never die
            pass


def _start_queue_watcher():
    threading.Thread(target=_queue_watcher, daemon=True).start()


@app.middleware("http")
async def _tenant_middleware(request: Request, call_next):
    """Resolve the session -> tenant contextvar; in hosted_mode gate /api/* and
    /files/* behind a session (UI_TOKEN owners and /api/auth/* pass through)."""
    token = request.cookies.get("ui_session") or ""
    if not token:
        auth = request.headers.get("authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
    user = tenants.resolve_session(WORKSPACE, token) if token else None
    request.state.tenant_user = user
    request.state.session_token = token
    tset = tenants.set_tenant(user["id"]) if user else None
    try:
        if tenants.hosted_mode(WORKSPACE) and not user:
            tok = _ui_token()
            owner_token = bool(tok) and (
                request.query_params.get("token") == tok or request.headers.get("x-ui-token") == tok)
            path = request.url.path
            if not owner_token:
                gated = (path.startswith("/api/") and not path.startswith("/api/auth/")
                         and not path.startswith("/api/health")) or path.startswith("/files/")
                if gated:
                    return JSONResponse({"error": "auth required", "auth": True}, status_code=401)
        response = await call_next(request)
    finally:
        if tset is not None:
            tenants.reset_tenant(tset)
    return response


def _state() -> StateDB:
    return StateDB(data_root() / "data" / "state.db")


def _library() -> LibraryDB:
    return LibraryDB(data_root() / "data" / "library.db")


# --- API: runs ---------------------------------------------------------------

@app.get("/api/state")
def api_state():
    st = _state()
    runs = []
    for r in st.list_runs():
        steps = {s["step"]: {"status": s["status"], "error": s["error"]}
                 for s in st.conn.execute(
                     "SELECT step, status, error FROM steps WHERE run_id=?", (r["run_id"],))}
        rd = runs_root() / r["run_id"]
        meta = {}
        try:
            meta = json.loads((rd / "metadata" / "metadata.json").read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            pass
        dur_sec = 0.0
        try:
            dur_sec = json.loads((rd / "video" / "assembly_result.json").read_text(encoding="utf-8")).get("duration_sec", 0.0)
        except Exception:
            pass
        timing = {}
        try:
            timing = json.loads((rd / "timing_report.json").read_text(encoding="utf-8"))
        except Exception:
            pass
        tokens_spent = st.usage_tokens(r["run_id"])
        cost_spent = st.usage_spent(r["run_id"])
        manifest_data = {}
        try:
            manifest_data = json.loads(r["manifest"])
        except Exception:
            pass

        best_title = meta.get("title") or manifest_data.get("topic") or r["run_id"]
        runs.append({
            "run_id": r["run_id"],
            "status": r["status"],
            "draft": bool((manifest_data.get("overrides") or {}).get("draft_plan")),
            "topic": manifest_data.get("topic", ""),
            "title": best_title,
            "steps": steps,
            "has_video": (rd / "video" / "episode.mp4").exists(),
            "has_preview": (rd / "visual" / "scenes.json").exists(),
            "has_timecodes": (rd / "video" / "timecodes.txt").exists(),
            "duration_sec": dur_sec,
            "tokens": tokens_spent,
            "cost_usd": cost_spent,
            "timing": timing,
            "export_dir": manifest_data.get("export_dir"),
            "created_at": r["created_at"],
        })
    st.close()

    lib = _library()
    topics = [dict(t) for t in lib.conn.execute("SELECT * FROM topics ORDER BY id DESC LIMIT 30")]
    episodes = []
    for e in lib.conn.execute("SELECT * FROM episodes ORDER BY run_id DESC LIMIT 30"):
        d = dict(e)
        row = _state().conn.execute("SELECT status FROM runs WHERE run_id=?", (d["run_id"],)).fetchone()
        failed = _state().conn.execute("SELECT COUNT(*) c FROM steps WHERE run_id=? AND status='failed'",
                                       (d["run_id"],)).fetchone()["c"]
        d["status"] = ("failed" if failed else row["status"]) if row else d["status"]
        episodes.append(d)
    refs = [dict(x) for x in lib.conn.execute('SELECT * FROM "references" ORDER BY id DESC LIMIT 30')]
    lib.close()
    return {"runs": runs, "topics": topics, "episodes": episodes, "references": refs}


@app.post("/api/episode")
def api_episode(body: dict, request: Request):
    topic = (body.get("topic") or "").strip()
    if len(topic) < 3:
        return JSONResponse({"error": "topic too short"}, status_code=400)
    user = _request_user(request)
    if tenants.hosted_mode(WORKSPACE) and user and not tenants.consume_credit(WORKSPACE, user):
        return JSONResponse({"error": "no credits", "credits": 0}, status_code=402)
    if tenants.hosted_mode(WORKSPACE) and _tenant_over_quota():
        return JSONResponse({"error": "disk quota exceeded — contact the administrator"}, status_code=507)
    num = 1
    for p in runs_root().glob("ep-*.manifest.yaml"):
        try:
            num = max(num, int(p.name.split("-")[1].split(".")[0]) + 1)
        except (ValueError, IndexError):
            pass
    # double-click guard: never overwrite an existing run
    while (runs_root() / f"ep-{num:04d}.manifest.yaml").exists() or _state().get_run(f"ep-{num:04d}"):
        num += 1
    run_id = f"ep-{num:04d}"
    overrides = {}
    pov = {k: v for k, v in (body.get("provider_overrides") or {}).items() if v}
    if pov:
        overrides["provider_overrides"] = pov
    mov = {k: v for k, v in (body.get("model_overrides") or {}).items() if v}
    if mov:
        overrides["model_overrides"] = mov
    if body.get("visual_preset"):
        overrides["visual_preset"] = body["visual_preset"]
    if body.get("export_dir"):
        overrides["export_dir"] = str(body["export_dir"]).strip()
    if body.get("music_mood"):
        overrides["music_mood"] = str(body["music_mood"]).strip()
    if isinstance(body.get("subtitles"), dict):
        overrides["subtitles"] = body["subtitles"]
    # draft preview (P5): script + scene plan WITHOUT synthesis/render — the
    # user reviews it, then POST /api/run/{id}/render re-runs m2/m3 for real
    until_step = None
    if body.get("draft"):
        overrides["draft_plan"] = True
        overrides.setdefault("visual", {})["plan_only"] = True
        until_step = "m3_visual"
    if body.get("preset"):
        presets = api_presets().get("presets", {})
        if body["preset"] in presets:
            overrides.update(presets[body["preset"]])
    manifest = {
        "run_id": run_id,
        "channel_id": body.get("channel_id", "my_channel"),
        "topic": topic,
        "format": "sleep_history",
        "target_minutes": min(int(body.get("target_minutes", 1)), 120),
        "language": body.get("language", "ru"),
        "reference_urls": body.get("reference_urls", []),
        "own_script": (body.get("own_script") or "").strip() or None,
        "script_notes": (body.get("script_notes") or body.get("notes") or "").strip() or None,
        "export_dir": (body.get("export_dir") or "").strip() or None,
        "profile": ("config/profiles/" + body["profile"] + ".yaml") if body.get("profile")
                   else "config/channel.profile.yaml",
        "overrides": overrides,
    }

    path = runs_root() / f"{run_id}.manifest.yaml"
    path.write_text(yaml.safe_dump(manifest, allow_unicode=True), encoding="utf-8")
    log_path = runs_root() / f"{run_id}.ui.log"
    run_cmd = [str(PY), "-u", "-m", "core.cli", "run", str(path)] \
        + (["--until", until_step] if until_step else [])
    if tenants.hosted_mode(WORKSPACE) and user:
        # P5-03: hosted launches go through the queue (host-wide slot limit)
        with _queue_lock:
            _run_queue.append({"run_id": run_id, "manifest_path": str(path),
                               "log_path": str(log_path), "env": _tenant_env(),
                               "cmd": run_cmd})
        _try_launch_queued()
        return {"run_id": run_id, "queued": True, "draft": bool(body.get("draft"))}
    log = log_path.open("w", encoding="utf-8")
    proc = subprocess.Popen(run_cmd,
                            stdout=log, stderr=subprocess.STDOUT, cwd=str(WORKSPACE),
                            env=_tenant_env())
    _procs[run_id] = proc
    return {"run_id": run_id}


@app.post("/api/run/{run_id}/resume")
def api_run_resume(run_id: str):
    r = _state().get_run(run_id)
    if not r:
        return JSONResponse({"error": "run not found"}, status_code=404)
    log = (runs_root() / f"{run_id}.ui.log").open("a", encoding="utf-8")
    proc = subprocess.Popen([str(PY), "-u", "-m", "core.cli", "resume", run_id],
                            stdout=log, stderr=subprocess.STDOUT, cwd=str(WORKSPACE),
                            env=_tenant_env())
    _procs[run_id] = proc
    return {"run_id": run_id, "status": "resumed"}


@app.post("/api/run/{run_id}/publish")
def api_run_publish(run_id: str, body: dict = None):
    body = body or {}
    r = _state().get_run(run_id)
    if not r:
        return JSONResponse({"error": "run not found"}, status_code=404)
    import json as _json

    manifest = _json.loads(r["manifest"])
    manifest["overrides"] = manifest.get("overrides") or {}
    manifest["overrides"]["provider_overrides"] = {"publish": body.get("provider", "youtube_api")}
    if body.get("publish_at"):
        manifest["overrides"]["publish_at"] = body["publish_at"]
    if body.get("visibility"):
        manifest["overrides"]["publish_visibility"] = body["visibility"]
    path = WORKSPACE / "runs" / f"{run_id}.manifest.yaml"
    path.write_text(yaml.safe_dump(manifest, allow_unicode=True), encoding="utf-8")
    # force m6 re-run: previous result (mock) must not block publishing
    st = _state()
    st.set_step(run_id, "m6_publish", "pending")
    st.close()
    log = (WORKSPACE / "runs" / f"{run_id}.ui.log").open("a", encoding="utf-8")
    subprocess.Popen([str(PY), "-u", "-m", "core.cli", "resume", run_id, "--until", "m6_publish"],
                     env=_tenant_env(),
                     stdout=log, stderr=subprocess.STDOUT, cwd=str(WORKSPACE))
    return {"ok": True, "note": "publishing started; if account is not yet connected Google OAuth will open"}


@app.post("/api/run/{run_id}/resume")
def api_resume(run_id: str):
    log = (WORKSPACE / "runs" / f"{run_id}.ui.log").open("a", encoding="utf-8")
    subprocess.Popen([str(PY), "-u", "-m", "core.cli", "resume", run_id],
                     stdout=log, stderr=subprocess.STDOUT, cwd=str(WORKSPACE),
                     env=_tenant_env())
    return {"ok": True}


@app.post("/api/transcript")
def api_transcript(body: dict):
    url = (body.get("url") or "").strip()
    if "youtube" not in url and "youtu.be" not in url:
        return JSONResponse({"error": "not a valid YouTube link"}, status_code=400)
    cmd = [str(PY), "-u", str(WORKSPACE / "tools" / "youtube_transcript.py"), url,
           "--lang", body.get("lang", "en")]
    if body.get("cookies"):
        cmd += ["--cookies", body["cookies"]]
    if body.get("cookies_from_browser"):
        cmd += ["--cookies-from-browser", body["cookies_from_browser"]]
    if body.get("proxy"):
        cmd += ["--proxy", body["proxy"]]
    else:
        ui_cfg_path = WORKSPACE / "config" / "ui_settings.yaml"
        if ui_cfg_path.exists():
            ui_cfg = yaml.safe_load(ui_cfg_path.read_text(encoding="utf-8")) or {}
            if ui_cfg.get("proxy_default"):
                cmd += ["--proxy", ui_cfg["proxy_default"]]
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(WORKSPACE), timeout=600)
    ok = proc.returncode == 0
    out = (proc.stdout + proc.stderr)[-1500:]
    if not ok and "Sign in to confirm" in out:
        out = ("YouTube requires authentication: export cookies.txt or specify cookies path. " + out) if "Sign in" in out else out
    return {"ok": ok, "output": out}


@app.get("/api/settings")
def api_settings():
    prof = yaml.safe_load((WORKSPACE / "config" / "channel.profile.yaml").read_text(encoding="utf-8"))
    provs = yaml.safe_load((WORKSPACE / "config" / "providers.yaml").read_text(encoding="utf-8"))
    provs_view = {"defaults": provs.get("defaults", {}),
                  "providers": list((provs.get("providers") or {}).keys()),
                  "budget_limit_usd": provs.get("budget_limit_usd")}
    return {"profile": prof, "providers": provs_view}


# --- API: providers / settings editing (BYOK, product vision §2) -------------

@app.get("/api/provider_options")
def api_provider_options():
    provs = yaml.safe_load((WORKSPACE / "config" / "providers.yaml").read_text(encoding="utf-8"))
    by_type: dict[str, list] = {}
    for name, cfg in (provs.get("providers") or {}).items():
        by_type.setdefault(cfg["type"], []).append(name)
    return {"by_type": by_type, "defaults": provs.get("defaults", {})}


@app.post("/api/providers/defaults")
def api_provider_defaults(body: dict):
    # tenant: seed the tenant copy from the host defaults, then write locally
    base = tenants.resolve_config(WORKSPACE, "config/providers.yaml")
    path = config_root() / "providers.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        (path.with_suffix(".yaml.bak")).write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    provs = (yaml.safe_load(base.read_text(encoding="utf-8")) or {}) if base.exists() else {"providers": {}}
    provs["defaults"] = body.get("defaults", {})
    path.write_text(yaml.safe_dump(provs, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return {"ok": True}


@app.post("/api/providers/add")
def api_provider_add(body: dict):
    pid = (body.get("id") or "").strip()
    if not pid or not pid.replace("_", "").isalnum():
        return JSONResponse({"error": "id: use letters, numbers, _"}, status_code=400)
    path = config_root() / "providers.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(tenants.resolve_config(WORKSPACE, "config/providers.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    path.with_suffix(".yaml.bak").write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    provs = yaml.safe_load(path.read_text(encoding="utf-8"))
    provs["providers"] = provs.get("providers") or {}
    entry = {"type": body.get("type", "llm"), "adapter": body.get("adapter", "openai_compatible")}
    for k in ("base_url", "model", "api_key_ref", "proxy", "ref_audio", "ref_text", "speaker"):
        if body.get(k):
            entry[k] = body[k]
    provs["providers"][pid] = entry
    if body.get("make_default"):
        provs["defaults"] = {**(provs.get("defaults") or {}), entry["type"]: pid}
    path.write_text(yaml.safe_dump(provs, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return {"ok": True}


@app.get("/api/profile_yaml")
def api_profile_yaml():
    return {"yaml": (config_root() / "channel.profile.yaml").read_text(encoding="utf-8")}


@app.post("/api/profile/save")
def api_profile_save(body: dict):
    path = config_root() / "channel.profile.yaml"
    path.with_suffix(".yaml.bak").write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    try:
        data = yaml.safe_load(body.get("yaml", ""))
        if not isinstance(data, dict):
            raise ValueError("root node must be a dict")
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": f"invalid YAML: {e}"}, status_code=400)
    path.write_text(body["yaml"], encoding="utf-8")
    return {"ok": True}


# --- API: presets, channel profiles, transcripts, ui settings -----------------

UI_CFG = WORKSPACE / "config" / "ui_settings.yaml"


@app.get("/api/presets")
def api_presets():
    PRESETS = config_root() / "presets"
    PRESETS.mkdir(parents=True, exist_ok=True)
    out = {}
    for f in PRESETS.glob("*.yaml"):
        out[f.stem] = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
    return {"presets": out}


@app.post("/api/presets/save")
def api_presets_save(body: dict):
    name = (body.get("name") or "").strip()
    if not name.replace("_", "").replace("-", "").isalnum():
        return JSONResponse({"error": "invalid preset name: use letters, numbers, _, -"}, status_code=400)
    PRESETS = config_root() / "presets"
    PRESETS.mkdir(parents=True, exist_ok=True)
    data = body.get("preset") or {}
    if not isinstance(data, dict):
        return JSONResponse({"error": "preset must be a dictionary of profile sections"}, status_code=400)
    (PRESETS / f"{name}.yaml").write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return {"ok": True}


@app.get("/api/profiles")
def api_profiles():
    PROFILES = config_root() / "profiles"
    PROFILES.mkdir(parents=True, exist_ok=True)
    return {"current": "config/channel.profile.yaml",
            "saved": [f.stem for f in PROFILES.glob("*.yaml")]}


@app.post("/api/profiles/save-as")
def api_profiles_save_as(body: dict):
    name = (body.get("name") or "").strip()
    if not name.replace("_", "").replace("-", "").isalnum():
        return JSONResponse({"error": "invalid profile name: use letters, numbers, _, -"}, status_code=400)
    PROFILES = config_root() / "profiles"
    PROFILES.mkdir(parents=True, exist_ok=True)
    (PROFILES / f"{name}.yaml").write_text(
        (config_root() / "channel.profile.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    return {"ok": True}


@app.get("/api/profile_yaml")
def api_profile_yaml(name: str | None = None):
    if name:
        return {"yaml": (config_root() / "profiles" / f"{name}.yaml").read_text(encoding="utf-8")}
    return {"yaml": (config_root() / "channel.profile.yaml").read_text(encoding="utf-8")}


@app.get("/api/transcripts")
def api_transcripts():
    d = data_root() / "transcripts"
    out = []
    if d.exists():
        for f in sorted(d.glob("*/transcript.md")):
            text = f.read_text(encoding="utf-8", errors="ignore")
            title = text.split("\n", 1)[0].lstrip("# ") if text else "?"
            out.append({"id": f.parent.name, "title": title,
                        "chars": len(text), "path": str(f)})
    return {"transcripts": out}


@app.get("/api/transcript_text")
def api_transcript_text(tid: str):
    f = data_root() / "transcripts" / tid / "transcript.md"
    if not f.exists():
        return JSONResponse({"error": "transcript not found"}, status_code=404)
    text = f.read_text(encoding="utf-8", errors="ignore")
    body = text.split("## Transcript", 1)[-1].strip() if "## Transcript" in text else text.split("## Расшифровка", 1)[-1].strip()
    return {"text": body}


@app.get("/api/ui_settings")
def api_ui_settings():
    if UI_CFG.exists():
        return yaml.safe_load(UI_CFG.read_text(encoding="utf-8")) or {}
    return {}


@app.post("/api/ui_settings")
def api_ui_settings_save(body: dict):
    UI_CFG.write_text(yaml.safe_dump(body, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return {"ok": True}


@app.get("/api/models")
def api_models(provider: str = ""):
    """Auto-fetch the model list of an openai-compatible provider (/v1/models)."""
    provs = yaml.safe_load((WORKSPACE / "config" / "providers.yaml").read_text(encoding="utf-8"))
    if not provider:
        provider = provs.get("defaults", {}).get("llm", "openrouter")

    curated = {
        "openrouter": [
            "google/gemini-2.0-flash-exp:free",
            "meta-llama/llama-3.3-70b-instruct:free",
            "qwen/qwen-2.5-72b-instruct:free",
            "mistralai/mistral-small-24b-instruct-2501:free",
            "deepseek/deepseek-r1:free",
            "deepseek/deepseek-chat:free",
            "nvidia/llama-3.1-nemotron-70b-instruct:free",
        ],
        "b_ai": [
            "mimo-v2.5",
            "mimo-v2.6-flash",
            "mimo-v2.6-pro",
        ],
        "mock": ["mock"],
    }

    cfg = (provs.get("providers") or {}).get(provider)
    if not cfg:
        return {"models": curated.get(provider, curated["openrouter"])}

    from core.secrets import load_env
    from core.providers.router import _resolve_secret

    load_env(WORKSPACE / ".env")
    base = (cfg.get("base_url") or "").rstrip("/")
    if not base:
        return {"models": curated.get(provider, ["default"])}

    key = _resolve_secret(cfg.get("api_key_ref", "")) if cfg.get("api_key_ref") else ""
    import httpx

    try:
        r = httpx.get(f"{base}/models", headers={"Authorization": f"Bearer {key}"} if key else {}, timeout=15)
        data = r.json()
        ids = [m.get("id") for m in data.get("data", []) if m.get("id")]
        if ids:
            return {"models": ids}
    except Exception:
        pass

    return {"models": curated.get(provider, curated["openrouter"])}


@app.get("/api/tts_voices")
def api_tts_voices(provider: str = ""):
    """Return available voices list for TTS providers.
    (Клоны пользователя живут на /api/voices — см. ui/api_studio.py.)"""
    voices = {
        "smallest_ai": [
            {"id": "magnus", "name": "Magnus (Calm deep male, multilingual)", "lang": "multilingual", "engine": "smallest_ai"},
            {"id": "arman", "name": "Arman (Expressive male, multilingual)", "lang": "multilingual", "engine": "smallest_ai"},
            {"id": "nikita", "name": "Nikita (Soft narrative, multilingual)", "lang": "multilingual", "engine": "smallest_ai"},
            {"id": "emily", "name": "Emily (Calm female, en/multilingual)", "lang": "en/multilingual", "engine": "smallest_ai"},
            {"id": "jasmine", "name": "Jasmine (Soft female, en/multilingual)", "lang": "en/multilingual", "engine": "smallest_ai"},
        ],
        "silero": [
            {"id": "eugene", "name": "Eugene (Deep male, RU)", "lang": "ru", "engine": "silero"},
            {"id": "baya", "name": "Baya (Narrative female, RU)", "lang": "ru", "engine": "silero"},
            {"id": "kseniya", "name": "Kseniya (Calm female, RU)", "lang": "ru", "engine": "silero"},
            {"id": "aidar", "name": "Aidar (Male, RU)", "lang": "ru", "engine": "silero"},
            {"id": "xenia", "name": "Xenia (Female, RU)", "lang": "ru", "engine": "silero"},
        ],
        "chatterbox": [
            {"id": "default", "name": "Default voice reference", "lang": "multilingual", "engine": "chatterbox"},
        ],
        "mock_tts": [
            {"id": "mock_voice", "name": "Mock voice", "lang": "all", "engine": "mock_tts"},
        ]
    }
    if not provider:
        provs = yaml.safe_load((WORKSPACE / "config" / "providers.yaml").read_text(encoding="utf-8"))
        provider = provs.get("defaults", {}).get("tts", "smallest_ai")
    return {"voices": voices.get(provider, voices["smallest_ai"])}



# --- API: notes (deep markdown + shallow quick comments), antidetect, publish ---

@app.get("/api/notes")
def api_notes():
    import sys

    sys.path.insert(0, str(WORKSPACE / "tools" / "notes"))
    import manager as notes_mgr

    return {"files": notes_mgr.list_notes(data_root() / "notes")}


@app.get("/api/notes/file")
def api_notes_file(path: str):
    import sys

    sys.path.insert(0, str(WORKSPACE / "tools" / "notes"))
    import manager as notes_mgr

    try:
        return {"path": path, "content": notes_mgr.read(path, root=data_root() / "notes")}
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@app.post("/api/notes/save")
def api_notes_save(body: dict):
    import sys

    sys.path.insert(0, str(WORKSPACE / "tools" / "notes"))
    import manager as notes_mgr

    try:
        notes_mgr.write(body["path"], body["content"])
        return {"ok": True}
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@app.post("/api/notes/quick")
def api_notes_quick(body: dict):
    lib = _library()
    nid = lib.add_note(body.get("scope", "episode"), body.get("ref_id"), body.get("body", ""))
    lib.close()
    return {"ok": True, "id": nid}


@app.get("/api/antidetect")
def api_antidetect():
    import json as _json
    import subprocess

    f = WORKSPACE / "grey_plugins" / "antidetect" / ".." / "proxy_kit" / "links.json"
    mgr = WORKSPACE / "grey_plugins" / "antidetect" / "manager.py"
    profiles = []
    pf = WORKSPACE / "grey_plugins" / "antidetect" / "profiles.json"
    if pf.exists():
        profiles = _json.loads(pf.read_text(encoding="utf-8")).get("profiles", [])
    return {"profiles": profiles, "cli": str(mgr)}


@app.post("/api/antidetect/add")
def api_antidetect_add(body: dict):
    import json as _json

    pf = WORKSPACE / "grey_plugins" / "antidetect" / "profiles.json"
    cfg = _json.loads(pf.read_text(encoding="utf-8")) if pf.exists() else {"profiles": []}
    pid = (body.get("id") or "").strip()
    if not pid or not body.get("proxy"):
        return JSONResponse({"error": "id and proxy required"}, status_code=400)
    cfg["profiles"].append({"id": pid, "label": body.get("label", ""), "proxy": body["proxy"]})
    pf.write_text(_json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True}


@app.get("/api/publish_status")
def api_publish_status():
    """Readiness check for YouTube publishing (no login performed)."""
    checks = {}
    try:
        import googleapiclient  # noqa: F401

        checks["google_libs"] = True
    except ImportError:
        checks["google_libs"] = False
    checks["client_secret"] = any(WORKSPACE.glob("client_secret*.json"))
    acc = WORKSPACE / "config" / "accounts.yaml"
    checks["accounts_configured"] = acc.exists()
    if acc.exists():
        accd = yaml.safe_load(acc.read_text(encoding="utf-8")) or {}
        accs = accd.get("accounts") or []
        checks["accounts_count"] = len(accs)
        checks["proxies_set"] = all(a.get("proxy") for a in accs)
    else:
        checks["accounts_count"] = 0
        checks["proxies_set"] = False
    ready = checks["google_libs"] and checks["client_secret"] and checks["accounts_configured"]
    return {"ready": ready, "checks": checks,
            "howto": ("1) console.cloud.google.com -> Create Project -> Enable YouTube Data API v3 -> "
                      "OAuth client ID (Desktop) -> download client_secret.json to pipeline/. "
                      "2) Fill config/accounts.yaml (configure proxies per channel). "
                      "3) First OAuth run will open browser for authentication.")}


@app.post("/api/env_save")
def api_env_save(body: dict):
    from core.envstore import save_key

    key = (body.get("key") or "").strip()
    if not key.replace("_", "").isalnum():
        return JSONResponse({"error": "invalid key name"}, status_code=400)
    save_key(WORKSPACE / ".env", key, (body.get("value") or "").strip())
    from core.secrets import load_env

    load_env(WORKSPACE / ".env")
    return {"ok": True}


# --- extra API (library CRUD, batch, digest, provider test, budget) ---
from ui import api_extra  # noqa: E402  (needs app/symbols defined above)

# --- remote browser (phone control): CDP screencast -> websocket -------------

_remote = {"page": None, "ctx": None, "pw": None, "clients": set(), "last": None, "loop": None}


@app.websocket("/ws/remote")
async def ws_remote(ws: WebSocket):
    """Phone-side remote browser: first message = {"action":"connect","profile":...};
    then frames stream out; client sends tap/scroll/nav/url events."""
    tok = _ui_token()
    if tok and ws.query_params.get("token") != tok:
        await ws.accept()
        await ws.close(code=1008)
        return
    if tenants.hosted_mode(WORKSPACE) and not tok:
        # hosted gate for the websocket (HTTP middleware does not cover WS)
        sid = ws.cookies.get("ui_session") or ""
        if not tenants.resolve_session(WORKSPACE, sid):
            await ws.accept()
            await ws.close(code=1008)
            return
    await ws.accept()
    import asyncio
    import base64

    # stale session guard: if the previous browser died (killed/timeout), relaunch
    if _remote["page"] is not None:
        try:
            if not _remote["ctx"].browser.is_connected():
                _remote["page"] = None
        except Exception:  # noqa: BLE001
            _remote["page"] = None
    if _remote["page"] is None:
        from playwright.async_api import async_playwright

        _remote["pw"] = await async_playwright().start()
        profile = WORKSPACE / "runs" / "remote_profile"
        profile.parent.mkdir(parents=True, exist_ok=True)
        _remote["ctx"] = await _remote["pw"].chromium.launch_persistent_context(
            str(profile), headless=True, viewport={"width": 1280, "height": 720})
        _remote["page"] = _remote["ctx"].pages[0] if _remote["ctx"].pages             else await _remote["ctx"].new_page()
        # consent bypass cookies for youtube (SOCS=CAI / CONSENT=YES+)
        await _remote["ctx"].add_cookies([
            {"name": "SOCS", "value": "CAE", "domain": ".youtube.com", "path": "/"},
            {"name": "SOCS", "value": "CAE", "domain": ".google.com", "path": "/"},
            {"name": "CONSENT", "value": "YES+cb.20260101-00-p0.ru+FX+000",
             "domain": ".youtube.com", "path": "/"},
        ])
        await _remote["page"].goto("https://youtube.com", timeout=60000)

    # initial frame via one-shot screenshot (screencast only fires on repaint)
    shot = await _remote["page"].screenshot(type="jpeg", quality=55)
    _remote["last"] = base64.b64encode(shot).decode()
    await ws.send_text(json.dumps({"type": "frame", "data": _remote["last"]}))

    cdp = await _remote["page"].context.new_cdp_session(_remote["page"])

    def on_frame(params):
        # MUST ack, or chromium stops sending frames after the first batch
        _remote["last"] = params.get("data", "")
        sid = params.get("sessionId")
        if sid:
            asyncio.ensure_future(cdp.send("Page.screencastFrameAck", {"sessionId": sid}))
    cdp.on("Page.screencastFrame", on_frame)
    await cdp.send("Page.startScreencast", {"format": "jpeg", "quality": 55, "everyNthFrame": 2})

    stop = asyncio.Event()

    async def pump():
        # broadcast the latest frame to every connected client (phone + PC)
        while not stop.is_set():
            if _remote["last"]:
                dead = []
                for client in list(_remote["clients"]):
                    try:
                        await client.send_text(json.dumps({"type": "frame", "data": _remote["last"]}))
                    except Exception:  # noqa: BLE001
                        dead.append(client)
                for c in dead:
                    _remote["clients"].discard(c)
            await asyncio.sleep(0.25)
    task = asyncio.create_task(pump())
    _remote["clients"].add(ws)
    async def navigate(url: str, target=None):
        target = target or ws
        nl = chr(10)
        if not url.startswith("http"):
            url = "https://" + url
        try:
            await target.send_text(json.dumps({"type": "status", "text": "navigating to " + url}))
            await page.goto(url, timeout=60000, wait_until="domcontentloaded")
            await page.wait_for_timeout(2500)
            # auto-dismiss consent (any locale)
            for _ in range(4):  # consent renders late and may live in frames — retry
                for fr in page.frames:
                    try:
                        await fr.evaluate("""() => {
                            document.querySelectorAll('tp-yt-iron-overlay-backdrop, #dialog').forEach(e => e.remove());
                            const accept = [...document.querySelectorAll('tp-yt-paper-button, button')]
                                .find(b => /принять все|accept all|alle akzeptieren/i.test(b.textContent||''));
                            if (accept) accept.click();
                        }""")
                    except Exception:  # noqa: BLE001 — frame may be gone
                        pass
                await page.wait_for_timeout(1500)
            await page.evaluate("() => { const d = document.documentElement; d.style.opacity = '0.99'; requestAnimationFrame(() => d.style.opacity = '1'); }")
            await target.send_text(json.dumps({"type": "status", "text": "ready"}))
        except Exception as e:  # noqa: BLE001 — report, keep session alive
            await target.send_text(json.dumps({"type": "status", "text": "navigation error: " + str(e)[:120]}))

    try:
        while True:
            msg = await ws.receive_text()
            data = json.loads(msg)
            page = _remote["page"]
            act = data.get("action")
            if act == "connect":
                asyncio.create_task(navigate("https://www.youtube.com"))
            elif act == "use_profile":
                pid = data.get("profile", "")
                ad_profiles = {}
                pf = WORKSPACE / "grey_plugins" / "antidetect" / "profiles.json"
                if pf.exists():
                    ad_profiles = {p["id"]: p for p in json.loads(pf.read_text(encoding="utf-8")).get("profiles", [])}
                prof = ad_profiles.get(pid)
                proxy = prof.get("proxy") if prof else None
                await _remote["ctx"].close()
                _remote["page"] = None
                _remote["ctx"] = await _remote["pw"].chromium.launch_persistent_context(
                    str(WORKSPACE / "runs" / "remote_profiles" / pid),
                    headless=True, viewport={"width": 1280, "height": 720},
                    proxy={"server": proxy} if proxy else None)
                _remote["page"] = _remote["ctx"].pages[0] if _remote["ctx"].pages                     else await _remote["ctx"].new_page()
                await _remote["ctx"].add_cookies([
                    {"name": "SOCS", "value": "CAE", "domain": ".youtube.com", "path": "/"}])
                await ws.send_text(json.dumps({"type": "status", "text": "profile: " + pid}))
                asyncio.create_task(navigate("https://www.youtube.com", ws))
            elif act == "tap":
                await page.mouse.click(float(data["x"]), float(data["y"]))
            elif act == "scroll":
                await page.mouse.wheel(0, float(data.get("dy", 0)))
            elif act == "back":
                await page.go_back()
            elif act == "url":
                asyncio.create_task(navigate(data.get("url", "")))
    except Exception:  # noqa: BLE001 — client disconnected
        pass
    stop.set()
    task.cancel()
    _remote["clients"].discard(ws)


# --- community plugins / MCP --------------------------------------------------

PLUGINS_DIR = WORKSPACE / "community_plugins"


@app.get("/api/plugins")
def api_plugins(request: Request):
    """P2 groundwork: plugin registry. Hosted mode: admin-only (plugins run
    with process rights — a real sandbox is a later step; community plugins
    stay a self-host feature)."""
    if tenants.hosted_mode(WORKSPACE):
        user = getattr(request.state, "tenant_user", None)
        if not user or user.get("role") != "admin":
            return JSONResponse({"error": "admin only (hosted mode)"}, status_code=403)
    out = []
    if PLUGINS_DIR.exists():
        for mf in sorted(PLUGINS_DIR.glob("*/plugin.json")):
            try:
                meta = json.loads(mf.read_text(encoding="utf-8"))
                meta.setdefault("version", "1.0.0")
                out.append({**meta, "folder": mf.parent.name})
            except json.JSONDecodeError:
                out.append({"folder": mf.parent.name, "error": "malformed plugin.json"})
    return {"plugins": out, "dir": str(PLUGINS_DIR)}


@app.post("/api/plugins/install")
def api_plugins_install(body: dict, request: Request):
    if tenants.hosted_mode(WORKSPACE):
        user = getattr(request.state, "tenant_user", None)
        if not user or user.get("role") != "admin":
            return JSONResponse({"error": "admin only (hosted mode)"}, status_code=403)
    try:
        meta = json.loads(body.get("manifest", ""))
        if "id" not in meta or "type" not in meta:
            raise ValueError("plugin.json requires id and type fields")
        meta.setdefault("version", "1.0.0")
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": "invalid manifest: " + str(e)}, status_code=400)
    folder = PLUGINS_DIR / meta["id"]
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "plugin.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "version": meta["version"], "note": "clone plugin files to " + str(folder)}


@app.get("/api/modules")
def api_modules():
    """P1 groundwork: machine-readable descriptors of the pipeline stages."""
    from core.module_descriptors import get_descriptors

    return {"modules": get_descriptors()}


# --- static ------------------------------------------------------------------

@app.get("/api/health")
def api_health():
    """Public health probe for uptime monitors (reveals nothing about data)."""
    return {"ok": True, "uptime_boot": BOOT_ID}


@app.get("/")
def index():
    # cache-proof entry: bounce every load through a unique path so no
    # browser (or in-app webview) can serve a stale copy
    from fastapi.responses import RedirectResponse

    return RedirectResponse(f"/app?{BOOT_ID}", status_code=307)


@app.get("/app")
def app_page():
    return FileResponse(WORKSPACE / "ui" / "static" / "index.html",
                        headers={"Cache-Control": "no-store, max-age=0"})


app.mount("/static", StaticFiles(directory=WORKSPACE / "ui" / "static"), name="static")


def _safe_file(base: Path, rel: str):
    base = base.resolve()
    f = (base / rel).resolve()
    if base != f and base not in f.parents:
        return JSONResponse({"error": "invalid path"}, status_code=400)
    if not f.is_file():
        return JSONResponse({"error": "not found"}, status_code=404)
    return FileResponse(f)


@app.get("/files/runs/{rel:path}")
def files_runs(rel: str):
    (runs_root() / "_uploads").mkdir(parents=True, exist_ok=True)
    return _safe_file(runs_root(), rel)


@app.get("/files/transcripts/{rel:path}")
def files_transcripts(rel: str):
    (data_root() / "transcripts").mkdir(parents=True, exist_ok=True)
    return _safe_file(data_root() / "transcripts", rel)


_start_queue_watcher()


def _start_watched_watcher():
    """5d: watched-folder queue — scans only when enabled in ui_settings."""
    def _loop():
        try:
            from ui.api_extra import _watched_watcher
            _watched_watcher()
        except Exception:  # noqa: BLE001
            pass
    threading.Thread(target=_loop, daemon=True).start()


_start_watched_watcher()


def main(port: int = 8765, host: str = "127.0.0.1"):
    import socket
    import uvicorn
    import webbrowser

    if host in ("0.0.0.0", ""):  # phone/tablet on the same Wi-Fi can open the LAN URL
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            lan = s.getsockname()[0]
            s.close()
            print(f"[ui] LAN access from phone/tablet on same Wi-Fi: http://{lan}:{port}")
        except OSError:
            pass
    threading.Timer(1.0, lambda: webbrowser.open(f"http://127.0.0.1:{port}")).start()
    uvicorn.run(app, host=host or "127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
