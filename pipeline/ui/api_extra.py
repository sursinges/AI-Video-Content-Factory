"""Extra UI API: library CRUD, batch series, transcript digest, provider test,
budget. Imported at the end of ui/server.py (all server symbols available)."""

import json
import subprocess
import threading
import time
from pathlib import Path

import yaml
import shutil

from fastapi import Request
from starlette.responses import JSONResponse

from ui.server import (WORKSPACE, PY, _state, _library, app, api_presets, runs_root, data_root, config_root, load_env_ctx)

BATCH: dict = {"running": False, "done": 0, "total": 0, "current": ""}


@app.post("/api/topics/add")
def api_topics_add(body: dict):
    lib = _library()
    tid = lib.add_topic(body.get("channel_id", "my_channel"),
                        (body.get("title") or "").strip(),
                        status=body.get("status", "idea"),
                        source=body.get("source", "ui"))
    lib.close()
    return {"ok": True, "id": tid}


@app.post("/api/topics/status")
def api_topics_status(body: dict):
    lib = _library()
    lib.conn.execute("UPDATE topics SET status=? WHERE id=?", (body.get("status", "idea"), body["id"]))
    lib.conn.commit()
    lib.close()
    return {"ok": True}


@app.post("/api/refs/add")
def api_refs_add(body: dict):
    lib = _library()
    lib.conn.execute(
        'INSERT INTO "references" (channel_id, kind, path, notes) VALUES (?, ?, ?, ?)',
        (body.get("channel_id", "my_channel"), body.get("kind", "video"),
         body.get("path", ""), body.get("notes", "")))
    lib.conn.commit()
    lib.close()
    return {"ok": True}


@app.post("/api/budget")
def api_budget(body: dict):
    path = WORKSPACE / "config" / "providers.yaml"  # host-global: budget protects the HOST wallet
    path.with_suffix(".yaml.bak").write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    provs = yaml.safe_load(path.read_text(encoding="utf-8"))
    provs["budget_limit_usd"] = float(body.get("budget_limit_usd", 0))
    path.write_text(yaml.safe_dump(provs, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return {"ok": True}


@app.get("/api/batch_status")
def api_batch_status():
    return BATCH


@app.post("/api/batch")
def api_batch(body: dict):
    topics = [t.strip() for t in (body.get("topics") or "").splitlines() if t.strip()]
    if not topics:
        return JSONResponse({"error": "empty topic list"}, status_code=400)
    if BATCH["running"]:
        return JSONResponse({"error": "series batch already in progress"}, status_code=409)

    def worker():
        BATCH.update(running=True, done=0, total=len(topics), current="")
        for i, topic in enumerate(topics):
            BATCH["current"] = topic
            num = 1
            for p in (runs_root()).glob("ep-*.manifest.yaml"):
                try:
                    num = max(num, int(p.name.split("-")[1].split(".")[0]) + 1)
                except (ValueError, IndexError):
                    pass
            run_id = f"ep-{num:04d}"
            manifest = {"run_id": run_id,
                        "channel_id": body.get("channel_id", "my_channel"),
                        "topic": topic, "format": "sleep_history",
                        "target_minutes": min(int(body.get("target_minutes", 1)), 60),
                        "language": body.get("language", "ru"), "reference_urls": [],
                        "profile": "config/channel.profile.yaml", "overrides": {}}
            path = runs_root() / f"{run_id}.manifest.yaml"
            path.write_text(yaml.safe_dump(manifest, allow_unicode=True), encoding="utf-8")
            subprocess.run([str(PY), "-u", "-m", "core.cli", "run", str(path)],
                           capture_output=True, cwd=str(WORKSPACE))
            BATCH["done"] = i + 1
        BATCH["running"] = False
        BATCH["current"] = ""

    threading.Thread(target=worker, daemon=True).start()
    return {"ok": True, "total": len(topics)}


@app.post("/api/transcript_digest")
def api_transcript_digest(body: dict):
    tr_dir = data_root() / "transcripts" / body.get("tid", "")
    f = tr_dir / "transcript.md"
    if not f.exists():
        return JSONResponse({"error": "transcript not found"}, status_code=404)
    raw = f.read_text(encoding="utf-8", errors="ignore").split("## Transcript", 1)[-1].strip()[:12000]
    st = _state()
    provs = yaml.safe_load((WORKSPACE / "config" / "providers.yaml").read_text(encoding="utf-8"))
    from core.providers.router import Router

    router = Router(provs, st, "digest", runs_root() / "_digest")
    nl = chr(10)
    prompt = ("You are an expert video editor and researcher. Below is a video transcript. Produce a CONCISE BRIEF "
              "to write an ORIGINAL script on this topic: 1) Core ideas and narrative structure "
              "(do not transcribe verbatim); 2) Verified facts that can be referenced; "
              "3) Audience retention hooks; 4) One-line topic summary. "
              "Do NOT copy author phrasing — focus purely on ideas and insights."
              + nl + nl + "TRANSCRIPT:" + nl + raw)
    try:
        resp = router.call("llm", {"prompt": prompt, "temperature": 0.4})
        text = resp.get("text", "")
    except Exception as e:  # noqa: BLE001
        st.close()
        return JSONResponse({"error": "LLM unavailable: " + str(e)}, status_code=502)
    st.close()
    out_md = tr_dir / "digest.md"
    out_md.write_text("# Transcript Digest" + nl + nl + text, encoding="utf-8")
    return {"ok": True, "brief": text, "path": str(out_md)}


@app.post("/api/clean_script")
def api_clean_script(body: dict):
    from core.script_cleaner import clean_script_text, parse_subtitles_file

    raw = body.get("text", "")
    if body.get("is_subtitles") or "-->" in raw:
        cleaned = parse_subtitles_file(raw)
    else:
        cleaned = clean_script_text(raw)
    return {"ok": True, "text": cleaned, "char_count": len(cleaned)}


@app.post("/api/adapt_script")
def api_adapt_script(body: dict):
    from core.script_cleaner import clean_script_text, parse_subtitles_file
    from core.adapt_engine import run_script_adaptation
    from core.providers.router import Router

    raw = body.get("text", "")
    if not raw.strip():
        return JSONResponse({"error": "script text is empty"}, status_code=400)

    if body.get("is_subtitles") or "-->" in raw:
        cleaned_source = parse_subtitles_file(raw)
    else:
        cleaned_source = clean_script_text(raw)

    prof_file = body.get("profile")
    prof_path = (config_root() / "profiles" / f"{prof_file}.yaml") if prof_file \
        else (config_root() / "channel.profile.yaml")
    profile = {}
    if prof_path.exists():
        profile = yaml.safe_load(prof_path.read_text(encoding="utf-8")) or {}

    load_env_ctx()

    st = _state()
    provs = yaml.safe_load((WORKSPACE / "config" / "providers.yaml").read_text(encoding="utf-8"))

    if body.get("provider"):
        provs.setdefault("defaults", {})["llm"] = body["provider"]
    selected_p = provs.get("defaults", {}).get("llm", "openrouter")
    if body.get("model"):
        m = str(body["model"]).strip()
        if selected_p == "b_ai" and ":free" in m:
            m = "mimo-v2.5"
        elif selected_p == "openrouter" and m == "mimo-v2.5":
            m = "z-ai/glm-5.2:free"
        if selected_p in provs.get("providers", {}):
            provs["providers"][selected_p]["model"] = m

    router = Router(provs, st, "adapt", runs_root() / "_adapt")
    try:
        res = run_script_adaptation(
            source_text=cleaned_source,
            profile=profile,
            router=router,
            workspace=WORKSPACE,
            target_minutes=body.get("target_minutes"),
            script_notes=(body.get("script_notes") or body.get("notes") or "").strip(),
            language=body.get("language") or profile.get("language", "ru"),
        )
    except Exception as e:
        st.close()
        return JSONResponse({"error": f"LLM error: {e}"}, status_code=502)
    st.close()

    if res.get("error"):
        return JSONResponse({"error": res["error"]}, status_code=500)

    return res


@app.post("/api/cover/generate")
def api_cover_generate(body: dict):
    """Cover studio: generate a cover variant via the image provider
    (neural nets) + text overlay. Variants are kept, never auto-overwritten."""
    run_id = body.get("run_id", "")
    run_dir = runs_root() / run_id
    if not (run_dir / "metadata" / "metadata.json").exists():
        return JSONResponse({"error": "run has no metadata"}, status_code=404)
    meta = json.loads((run_dir / "metadata" / "metadata.json").read_text(encoding="utf-8"))
    covers = run_dir / "metadata" / "covers"
    covers.mkdir(parents=True, exist_ok=True)
    n = len(list(covers.glob("cover_*"))) + 1
    out = covers / f"cover_{n:02d}.png"

    provs = yaml.safe_load((WORKSPACE / "config" / "providers.yaml").read_text(encoding="utf-8"))
    from core.secrets import load_env
    from core.providers import router as router_mod

    load_env_ctx()
    registry = router_mod.build_registry(provs, router_mod._resolve_secret)
    provider_id = body.get("provider") or (provs.get("defaults") or {}).get("image")
    provider = registry.get("image/" + (provider_id or ""))
    if provider is None:
        return JSONResponse({"error": "image provider not found"}, status_code=400)
    prompt = body.get("prompt") or "flat vector night scene, calm sleep mood, dark palette, no text"
    text_prompt = (body.get("text_prompt") or "").strip()
    overlay_text = (body.get("overlay") or "").strip()
    brand = _brand_cover_suffix()
    if brand:
        prompt = f"{prompt}, {brand}"
    if overlay_text and text_prompt:
        # нейросеть рисует сам текст поверх обложки (шрифт/расположение задаёт text_prompt)
        prompt = f"{prompt}, large bold title text \"{overlay_text}\", {text_prompt}"
    try:
        res = provider.execute({"prompt": prompt, "out_path": str(out) + ".tmp.png",
                                "width": 1280, "height": 720})
    except Exception as e:  # noqa: BLE001 — report generation failures clearly
        return JSONResponse({"error": str(e)}, status_code=502)
    from core.media import drawtext_card
    import shutil

    overlay = body.get("overlay") or (meta.get("thumbnail") or {}).get("text_overlay", "")
    final = covers / f"cover_{n:02d}.png"
    drawtext_card.__globals__  # noqa: B018
    if Path(str(out) + ".tmp.png").exists():
        shutil.copy(str(out) + ".tmp.png", final)
        Path(str(out) + ".tmp.png").unlink()
    if overlay:
        from core.media import ff

        font = r"C:/Windows/Fonts/arialbd.ttf".replace(":", r"\:")
        import re as _re
        safe = _re.sub(r"[^\w\s.,!?:-]", "", overlay)[:40] or "COVER"
        tmp_out = final.with_suffix(".draw.png")
        ff(["-i", str(final),
            "-vf", (f"drawtext=fontfile='{font}':text='{safe}':fontcolor=0xE1C049:fontsize=110:"
                    f"borderw=6:bordercolor=0x0C0A26:x=(w-text_w)/2:y=h-text_h-60"),
            "-frames:v", "1", "-y", str(tmp_out)])
        tmp_out.replace(final)
    return {"ok": True, "path": str(final)}


@app.get("/api/cover/list")
def api_cover_list(run_id: str):
    covers = runs_root() / run_id / "metadata" / "covers"
    if not covers.exists():
        return {"covers": []}
    return {"covers": [str(f.relative_to(runs_root())).replace("\\", "/")
                       for f in sorted(covers.glob("cover_*"))]}


@app.post("/api/cover/set")
def api_cover_set(body: dict):
    run_id = body.get("run_id", "")
    run_dir = runs_root() / run_id
    chosen = body.get("path", "")
    if not chosen.startswith("runs/"):
        return JSONResponse({"error": "path outside run directory"}, status_code=400)
    src = WORKSPACE / chosen
    if not src.exists():
        return JSONResponse({"error": "file not found"}, status_code=404)
    import shutil

    final = run_dir / "metadata" / "thumbnail.png"
    shutil.copy(src, final)
    mf = run_dir / "metadata" / "metadata.json"
    meta = json.loads(mf.read_text(encoding="utf-8"))
    meta["thumbnail"]["asset"] = str(final)
    mf.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "asset": str(final)}


@app.get("/api/browser/profiles")
def api_browser_profiles():
    import json as _json

    pf = WORKSPACE / "grey_plugins" / "antidetect" / "profiles.json"
    profiles = _json.loads(pf.read_text(encoding="utf-8")).get("profiles", []) if pf.exists() else []
    return {"profiles": profiles}


@app.post("/api/browser/create")
def api_browser_create(body: dict):
    import json as _json

    pid = (body.get("id") or "").strip()
    if not pid or not body.get("proxy"):
        return JSONResponse({"error": "id and proxy required"}, status_code=400)
    pf = WORKSPACE / "grey_plugins" / "antidetect" / "profiles.json"
    cfg = _json.loads(pf.read_text(encoding="utf-8")) if pf.exists() else {"profiles": []}
    cfg["profiles"].append({"id": pid, "label": body.get("label", ""), "proxy": body["proxy"]})
    pf.write_text(_json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True}


@app.post("/api/browser/launch")
def api_browser_launch(body: dict):
    """Opens a REAL anti-detect browser window (Camoufox) on this machine
    under the chosen profile. Non-blocking."""
    import subprocess

    pid = body.get("profile", "")
    cmd = [str(PY), "-u", str(WORKSPACE / "grey_plugins" / "antidetect" / "manager.py"),
           "launch", pid, "--no-wait"]
    if body.get("url"):
        cmd += ["--url", body["url"]]
    subprocess.Popen(cmd, cwd=str(WORKSPACE))
    return {"ok": True, "note": "browser window launching on host"}


# --- run artifacts -----------------------------------------------------------

@app.get("/api/run/{run_id}/progress")
def api_run_progress(run_id: str):
    """Live run status for the run card: ordered pipeline steps + per-step timing."""
    rd = runs_root() / run_id
    if not rd.exists():
        return JSONResponse({"error": "run not found"}, status_code=404)
    st = _state()
    steps = [{"step": s["step"], "status": s["status"], "error": s["error"]}
             for s in st.conn.execute(
                 "SELECT step, status, error FROM steps WHERE run_id=? ORDER BY rowid", (run_id,))]
    st.close()
    timing = {}
    tf = rd / "timing_report.json"
    if tf.exists():
        try:
            timing = json.loads(tf.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            pass
    log_tail = ""
    logf = runs_root() / f"{run_id}.ui.log"
    if logf.exists():
        lines = logf.read_text(encoding="utf-8", errors="ignore").splitlines()
        log_tail = "\n".join(lines[-60:])
    from ui.server import _run_queue
    queued = any(j["run_id"] == run_id for j in _run_queue)
    return {"ok": True, "run_id": run_id, "steps": steps, "timing": timing,
            "log_tail": log_tail, "queued": queued}


@app.get("/api/run/{run_id}/script")
def api_run_script(run_id: str):
    f = runs_root() / run_id / "script" / "script.json"
    if not f.exists():
        return JSONResponse({"error": "script not found"}, status_code=404)
    script = json.loads(f.read_text(encoding="utf-8"))
    parts = [c["text"] for c in script.get("chunks", [])]
    return {"title": script.get("title_working", ""), "parts": parts}


@app.get("/api/run/{run_id}/usage")
def api_run_usage(run_id: str):
    f = runs_root() / run_id / "usage.jsonl"
    rows, total_tokens = [], 0
    if f.exists():
        for line in f.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
                rows.append(r)
                total_tokens += r.get("tokens", 0) or 0
            except json.JSONDecodeError:
                pass
    calls = {}
    for r in rows:
        k = f"{r.get('ptype')}/{r.get('provider')}"
        calls[k] = calls.get(k, 0) + 1
    return {"calls_total": len(rows), "calls": calls, "tokens": total_tokens}


@app.get("/api/run/{run_id}/scenes")
def api_run_scenes(run_id: str):
    f = runs_root() / run_id / "visual" / "scenes.json"
    if not f.exists():
        return {"scenes": []}
    scenes = json.loads(f.read_text(encoding="utf-8")).get("scenes", [])
    return {"scenes": [{"id": s["id"], "start": s["start"], "end": s["end"],
                        "asset": "/files/runs/" + run_id + "/visual/assets/" + Path(s["asset"]).name
                        if s.get("asset") else None} for s in scenes]}


@app.get("/api/accounts")
def api_accounts():
    acc = config_root() / "accounts.yaml"
    if not acc.exists():
        return {"accounts": [], "rotation": "manual"}
    d = yaml.safe_load(acc.read_text(encoding="utf-8")) or {}
    return {"accounts": d.get("accounts", []), "rotation": d.get("rotation", "manual")}


@app.post("/api/accounts/save")
def api_accounts_save(body: dict):
    acc = config_root() / "accounts.yaml"
    acc.write_text(yaml.safe_dump(body, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return {"ok": True}


@app.post("/api/proxykit/add")
def api_proxykit_add(body: dict):
    pid = (body.get("id") or "").strip()
    link = (body.get("link") or "").strip()
    if not pid or not link:
        return JSONResponse({"error": "id and link required"}, status_code=400)
    links = WORKSPACE / "grey_plugins" / "proxy_kit" / "links.json"
    data = json.loads(links.read_text(encoding="utf-8")) if links.exists() else {"links": {}}
    data["links"][pid] = link
    links.parent.mkdir(parents=True, exist_ok=True)
    links.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True}


@app.post("/api/proxykit/cmd")
def api_proxykit_cmd(body: dict):
    import subprocess as sp

    pid = body.get("id", "")
    cmd = body.get("cmd", "")
    if cmd not in ("up", "down", "test", "setup"):
        return JSONResponse({"error": "command: up|down|test|setup"}, status_code=400)
    args = [str(PY), "-u", str(WORKSPACE / "grey_plugins" / "proxy_kit" / "manager.py")]
    if cmd == "setup":
        proc = sp.run(args + ["setup"], capture_output=True, text=True, timeout=300)
        return {"ok": proc.returncode == 0, "output": (proc.stdout + proc.stderr)[-400:]}
    if cmd == "up":
        proc = sp.Popen(args + ["up", pid, "--port", str(body.get("port", 10808))],
                        cwd=str(WORKSPACE))
        return {"ok": True, "note": f"socks5://127.0.0.1:{body.get('port', 10808)} launching (xray)"}
    proc = sp.run(args + [cmd, pid], capture_output=True, text=True, timeout=120, cwd=str(WORKSPACE))
    return {"ok": proc.returncode == 0, "output": (proc.stdout + proc.stderr)[-400:]}


# --- static ---
def api_yt_secret(body: dict):
    from pathlib import Path

    src = Path(body.get("path", ""))
    if not src.exists():
        return JSONResponse({"error": "file not found: " + str(src)}, status_code=400)
    import shutil

    dst = WORKSPACE / "client_secret.json"
    shutil.copy(src, dst)
    return {"ok": True}


@app.post("/api/yt/connect")
def api_yt_connect(body: dict):
    import subprocess

    cmd = [str(PY), "-u", str(WORKSPACE / "tools" / "youtube_connect.py"),
           "--profile", body.get("profile", "acc1")]
    if body.get("proxy"):
        cmd += ["--proxy", body["proxy"]]
    from ui.server import _tenant_env
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(WORKSPACE), timeout=600,
                          env=_tenant_env())
    ok = proc.returncode == 0
    return {"ok": ok, "output": (proc.stdout + proc.stderr)[-800:]}


@app.get("/api/yt/status")
def api_yt_status():
    libs = False
    try:
        import googleapiclient  # noqa: F401

        libs = True
    except ImportError:
        pass
    secret = any(WORKSPACE.glob("client_secret*.json"))
    tokens_dir = data_root() / "data" / "tokens"
    tokens = sorted(tokens_dir.glob("*.json")) if tokens_dir.exists() else []
    return {"libs": libs, "secret": secret,
            "connected": [f.stem for f in tokens]}


@app.post("/api/provider_test")
def api_provider_test(body: dict):
    pid = body.get("provider", "")
    provs = yaml.safe_load((WORKSPACE / "config" / "providers.yaml").read_text(encoding="utf-8"))
    cfg = (provs.get("providers") or {}).get(pid)
    if not cfg:
        return JSONResponse({"error": "provider not found"}, status_code=404)
    ptype = cfg["type"]
    from core.secrets import load_env
    from core.providers import router as router_mod

    load_env_ctx()
    try:
        registry = router_mod.build_registry(provs, router_mod._resolve_secret)
        provider = registry[ptype + "/" + pid]
        t0 = time.time()
        test_dir = runs_root() / "_test"
        test_dir.mkdir(parents=True, exist_ok=True)
        if ptype == "llm":
            res = provider.execute({"prompt": "Reply with exactly one word: working"})
            detail = str(res.get("text", ""))[:80]
        elif ptype == "tts":
            out = test_dir / "tts.mp3"
            res = provider.execute({"text": "Voice synthesis test.", "out_path": str(out)})
            detail = "audio " + str(Path(res["audio_path"]).stat().st_size // 1024) + " KB"
        elif ptype == "image":
            out = test_dir / "img.png"
            res = provider.execute({"prompt": "flat vector night scene, calm, no text",
                                    "out_path": str(out), "width": 512, "height": 512})
            detail = "image " + str(Path(res["image_path"]).stat().st_size // 1024) + " KB"
        else:
            res = provider.execute({"query": "test",
                                    "out_path": str(test_dir / (pid + ".bin"))})
            detail = json.dumps(res)[:80]
        return {"ok": True, "sec": round(time.time() - t0, 1), "detail": detail}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)[:300]}


@app.get("/api/run/{run_id}/preview")
def api_run_preview(run_id: str):
    """Storyboard preview before/after assembly: list of scenes with assets, text, audio and effect."""
    rd = runs_root() / run_id
    if not rd.exists():
        return JSONResponse({"error": "прогон не найден"}, status_code=404)
    scenes_f = rd / "visual" / "scenes.json"
    scenes = []
    if scenes_f.exists():
        try:
            scenes = json.loads(scenes_f.read_text(encoding="utf-8")).get("scenes", [])
        except Exception:
            pass

    script_f = rd / "script" / "script.json"
    chunks = []
    if script_f.exists():
        try:
            chunks = json.loads(script_f.read_text(encoding="utf-8")).get("chunks", [])
        except Exception:
            pass

    def _format_tc(sec: float) -> str:
        s = int(round(sec))
        hh = s // 3600
        mm = (s % 3600) // 60
        ss = s % 60
        return f"{hh:02d}:{mm:02d}:{ss:02d}"

    items = []
    for i, s in enumerate(scenes):
        sc_id = s.get("id", f"s{i+1:03d}")
        asset_p = s.get("asset")
        asset_url = None
        if asset_p and Path(asset_p).exists():
            asset_url = f"/files/runs/{run_id}/visual/assets/{Path(asset_p).name}"

        part_audio = rd / "audio" / f"scene_{i+1:03d}.mp3"
        part_audio_url = f"/files/runs/{run_id}/audio/scene_{i+1:03d}.mp3" if part_audio.exists() else None

        clip_mp4 = rd / "video" / "_work" / f"scene_{i:03d}.mp4"
        clip_url = f"/files/runs/{run_id}/video/_work/scene_{i:03d}.mp4" if clip_mp4.exists() else None

        start_s = s.get("start", 0.0)
        end_s = s.get("end", 0.0)
        dur_s = max(round(end_s - start_s, 2), 0.0)

        items.append({
            "index": i + 1,
            "scene_id": sc_id,
            "start": start_s,
            "end": end_s,
            "duration_sec": dur_s,
            "start_tc": _format_tc(start_s),
            "end_tc": _format_tc(end_s),
            "timecode_range": f"{_format_tc(start_s)} - {_format_tc(end_s)}",
            "effect": s.get("effect", "zoom_in"),
            "text": (s.get("text") or s.get("text_ref") or (chunks[i]["text"] if i < len(chunks) else "")).replace("|", " ").strip(),
            "prompt": s.get("prompt", ""),
            "asset_url": asset_url,
            "audio_url": part_audio_url,
            "clip_url": clip_url,
        })


    has_video = (rd / "video" / "episode.mp4").exists()
    return {
        "run_id": run_id,
        "scenes_count": len(items),
        "has_video": has_video,
        "video_url": f"/files/runs/{run_id}/video/episode.mp4" if has_video else None,
        "scenes": items,
    }


@app.get("/api/run/{run_id}/timecodes")
def api_run_timecodes(run_id: str):
    """Accurate YouTube timecodes and structured mapping."""
    rd = runs_root() / run_id
    tc_txt = rd / "video" / "timecodes.txt"
    tc_json = rd / "video" / "timecodes.json"

    if not tc_txt.exists() and (rd / "visual" / "scenes.json").exists() and (rd / "audio" / "audio_result.json").exists():
        try:
            scenes_data = json.loads((rd / "visual" / "scenes.json").read_text(encoding="utf-8"))
            scenes = scenes_data.get("scenes", [])
            audio_res = json.loads((rd / "audio" / "audio_result.json").read_text(encoding="utf-8"))
            total_dur = audio_res.get("duration_sec", 0.0)
            base = [max(s.get("end", 0.0) - s.get("start", 0.0), 0.4) for s in scenes]
            FADE = 1.2
            k = max(len(scenes) - 1, 0)
            scale = (total_dur + FADE * k) / (sum(base) or 1.0)
            durations = [b * scale for b in base]
            t_cur = 0.0
            tc_lines, tc_items = [], []
            for i, s in enumerate(scenes):
                dur = durations[i]
                mm, ss = int(t_cur // 60), int(t_cur % 60)
                hh = int(mm // 60)
                tc_str = f"{hh:02d}:{mm%60:02d}:{ss:02d}" if hh > 0 else f"{mm:02d}:{ss:02d}"
                txt = (s.get("text") or s.get("text_ref") or "").replace("|", " ").strip()
                words = txt.split()
                stitle = " ".join(words[:7]) if words else f"Scene {i+1}"
                tc_lines.append(f"{tc_str} {stitle}")
                tc_items.append({
                    "index": i + 1,
                    "scene_id": s.get("id", f"s{i+1:03d}"),
                    "timecode": tc_str,
                    "start_sec": round(t_cur, 2),
                    "end_sec": round(t_cur + dur, 2),
                    "duration_sec": round(dur, 2),
                    "effect": s.get("effect", "zoom_in"),
                    "text": txt,
                    "asset": s.get("asset", "")
                })
                t_cur += (dur - FADE) if i < len(scenes) - 1 else dur
            (rd / "video").mkdir(parents=True, exist_ok=True)
            tc_txt.write_text("\n".join(tc_lines), encoding="utf-8")
            tc_json.write_text(json.dumps(tc_items, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

    txt_content = tc_txt.read_text(encoding="utf-8") if tc_txt.exists() else ""
    json_content = json.loads(tc_json.read_text(encoding="utf-8")) if tc_json.exists() else []
    return {
        "ok": True,
        "run_id": run_id,
        "text": txt_content,
        "items": json_content,
    }



@app.get("/api/run/{run_id}/metadata")
def api_run_metadata(run_id: str):
    """Generated metadata (title/description/tags/chapters) for the run card."""
    f = runs_root() / run_id / "metadata" / "metadata.json"
    if not f.exists():
        return JSONResponse({"error": "metadata not yet generated"}, status_code=404)
    return json.loads(f.read_text(encoding="utf-8"))


@app.get("/api/run/{run_id}/export_zip")
def api_run_export_zip(run_id: str):
    """Bundle the run's deliverables (video, timecodes, subs, thumbnail, metadata) into one ZIP."""
    import zipfile

    from fastapi.responses import FileResponse

    rd = runs_root() / run_id
    if not (rd / "video" / "episode.mp4").exists():
        return JSONResponse({"error": "video not yet assembled"}, status_code=400)
    zpath = rd / f"{run_id}_export.zip"
    files = [
        (rd / "video" / "episode.mp4", f"{run_id}.mp4"),
        (rd / "video" / "timecodes.txt", f"{run_id}_timecodes.txt"),
        (rd / "video" / "timecodes.json", f"{run_id}_timecodes.json"),
        (rd / "subtitles" / "subtitles.srt", f"{run_id}.srt"),
        (rd / "metadata" / "thumbnail.png", f"{run_id}_thumbnail.png"),
        (rd / "metadata" / "metadata.json", f"{run_id}_metadata.json"),
        (rd / "visual" / "scenes.json", f"{run_id}_scenes.json"),
    ]
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for src, arc in files:
            if src.exists():
                z.write(src, arc)
    return FileResponse(zpath, filename=zpath.name, media_type="application/zip")


@app.post("/api/run/{run_id}/export")
def api_run_export(run_id: str, body: dict):
    """Custom folder export for final video, timecodes, subtitles, and thumbnail."""
    target = (body.get("target_folder") or "").strip()
    if not target:
        return JSONResponse({"error": "target folder not specified"}, status_code=400)
    rd = runs_root() / run_id
    vid = rd / "video" / "episode.mp4"
    if not vid.exists():
        return JSONResponse({"error": "video not yet assembled"}, status_code=400)
    import shutil
    dest = Path(target)
    dest.mkdir(parents=True, exist_ok=True)
    exported = []
    shutil.copy2(vid, dest / f"{run_id}.mp4")
    exported.append(str(dest / f"{run_id}.mp4"))
    for name, suf in [("timecodes.txt", "_timecodes.txt"), ("timecodes.json", "_timecodes.json")]:
        f = rd / "video" / name
        if f.exists():
            shutil.copy2(f, dest / f"{run_id}{suf}")
            exported.append(str(dest / f"{run_id}{suf}"))
    thumb = rd / "metadata" / "thumbnail.png"
    if thumb.exists():
        shutil.copy2(thumb, dest / f"{run_id}_thumbnail.png")
        exported.append(str(dest / f"{run_id}_thumbnail.png"))
    srt = rd / "subtitles" / "subtitles.srt"
    if srt.exists():
        shutil.copy2(srt, dest / f"{run_id}.srt")
        exported.append(str(dest / f"{run_id}.srt"))
    return {"ok": True, "exported_files": exported, "folder": str(dest)}


@app.post("/api/assistant/chat")
def api_assistant_chat(body: dict):
    """AI director & editor chat grounded in ASSET_RULES.md."""
    message = (body.get("message") or "").strip()
    if not message:
        return JSONResponse({"error": "empty message"}, status_code=400)
    context_info = body.get("context") or ""
    rules_path = WORKSPACE / "config" / "ASSET_RULES.md"
    rules_text = rules_path.read_text(encoding="utf-8") if rules_path.exists() else ""

    system_prompt = (
        "You are a professional AI Director and Video Editor for AI-Video-Content-Factory.\n"
        "Your role is to advise the user on visual style, image prompts, voice selection, camera motion effects (zoom_in, zoom_out, pan_left_right, pan_right_left, tilt_up, tilt_down, handheld_drift, film_grain, vignette_focus, cinematic_contrast), and pacing.\n\n"
        "PROJECT GUIDELINES & STANDARDS:\n"
        f"{rules_text}\n\n"
        "Respond concisely, professionally, and actionably. When suggesting scene modifications, specify the exact effect and prompt."
    )
    user_prompt = f"Run/Scene Context:\n{context_info}\n\nUser Request:\n{message}"

    from core.secrets import load_env
    from core.providers import router as router_mod
    load_env_ctx()
    provs = yaml.safe_load((WORKSPACE / "config" / "providers.yaml").read_text(encoding="utf-8"))
    try:
        registry = router_mod.build_registry(provs, router_mod._resolve_secret)
        llm_default = provs.get("defaults", {}).get("llm", "openrouter_free")
        llm_prov = registry.get(f"llm/{llm_default}") or registry.get("llm/mock")
        res = llm_prov.execute({
            "prompt": f"{system_prompt}\n\nПользователь: {user_prompt}",
            "system": system_prompt,
        })
        reply_text = res.get("text", "")
        return {"ok": True, "reply": reply_text}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.post("/api/run/{run_id}/modify_scene")
def api_run_modify_scene(run_id: str, body: dict):
    """Selectively re-render a single scene's visual image, motion effect, or text,
    and fast-reassembles the video in seconds."""
    scene_idx = int(body.get("scene_index", 0))
    aspect = body.get("aspect", "effect")  # "effect" | "image" | "text"
    new_value = body.get("new_value", "")

    rd = runs_root() / run_id
    scenes_f = rd / "visual" / "scenes.json"
    if not scenes_f.exists():
        return JSONResponse({"error": "scenes not found"}, status_code=404)
    scenes_data = json.loads(scenes_f.read_text(encoding="utf-8"))
    scenes = scenes_data.get("scenes", [])
    if scene_idx < 0 or scene_idx >= len(scenes):
        return JSONResponse({"error": f"scene index {scene_idx} out of range"}, status_code=400)

    from core.media import (
        AVAILABLE_SCENE_EFFECTS,
        mix_and_master,
        mux,
        render_scene_clip,
        xfade_chain,
    )
    from modules.m3_visual.runner import _load_visual_preset

    sc = scenes[scene_idx]
    work_dir = rd / "video" / "_work"
    work_dir.mkdir(parents=True, exist_ok=True)

    if aspect == "effect":
        parts = [p.strip() for p in str(new_value).split("+") if p.strip()]
        if not parts or any(p not in AVAILABLE_SCENE_EFFECTS for p in parts):
            return JSONResponse({"error": f"unknown effect: {new_value}"}, status_code=400)
        sc["effect"] = "+".join(parts)
    elif aspect == "asset":
        new_path = str(new_value or "").strip()
        if not new_path:
            return JSONResponse({"error": "image path not specified"}, status_code=400)
        p = Path(new_path)
        if not p.is_absolute():
            p = (data_root() / new_path).resolve()
        if not p.exists():
            return JSONResponse({"error": "image file not found"}, status_code=400)
        sc["asset"] = str(p)
    elif aspect == "text":
        sc["text"] = str(new_value)
    elif aspect == "image":
        prompt = str(new_value) if new_value else sc.get("prompt", "")
        preset = _load_visual_preset("dark_history_cinematic")
        full_prompt = f"{prompt}, {preset['style_prompt']}"
        img_out = rd / "visual" / "assets" / f"{sc['id']}.jpg"
        from core.providers.vheer_browser import VheerBrowserProvider
        vheer = VheerBrowserProvider("vheer_browser", "image", {"headless": True}, resolve_secret=lambda r: "")
        try:
            res = vheer.execute({
                "prompt": full_prompt,
                "negative": preset["negative_prompt"],
                "out_path": str(img_out),
                "width": 1024,
                "height": 576,
            })
            sc["asset"] = res.get("image_path", str(img_out))
        except Exception:
            pass

    scenes_f.write_text(json.dumps(scenes_data, indent=2, ensure_ascii=False), encoding="utf-8")

    # Recalculate durations
    audio_res = json.loads((rd / "audio" / "audio_result.json").read_text(encoding="utf-8"))
    total_dur = audio_res["duration_sec"]
    base = [max(s.get("end", 0.0) - s.get("start", 0.0), 0.4) for s in scenes]
    FADE = 1.2
    k = max(len(scenes) - 1, 0)
    scale = (total_dur + FADE * k) / sum(base)
    durations = [b * scale for b in base]

    # Re-render ONLY this single scene clip
    clip_mp4 = work_dir / f"scene_{scene_idx:03d}.mp4"
    render_scene_clip(sc["asset"], clip_mp4, duration=durations[scene_idx], effect=sc["effect"], size="1920x1080")

    # Fast re-assembly via xfade
    scene_files = [work_dir / f"scene_{i:03d}.mp4" for i in range(len(scenes))]
    silent = work_dir / "video_silent.mp4"
    xfade_chain(scene_files, durations, silent, fade=FADE, size="1920x1080")

    # Mux with existing audio
    mixed = work_dir / "audio_mixed.m4a"
    final = rd / "video" / "episode.mp4"
    mux(silent, mixed, final)

    # Refresh timecodes
    t_cur = 0.0
    tc_lines, tc_items = [], []
    for i, s in enumerate(scenes):
        dur = durations[i]
        mm, ss = int(t_cur // 60), int(t_cur % 60)
        hh = int(mm // 60)
        tc_str = f"{hh:02d}:{mm%60:02d}:{ss:02d}" if hh > 0 else f"{mm:02d}:{ss:02d}"
        txt = (s.get("text") or s.get("text_ref") or "").replace("|", " ").strip()
        words = txt.split()
        stitle = " ".join(words[:7]) if words else f"Scene {i+1}"
        tc_lines.append(f"{tc_str} {stitle}")
        tc_items.append({
            "index": i + 1,
            "scene_id": s.get("id", f"s{i+1:03d}"),
            "timecode": tc_str,
            "start_sec": round(t_cur, 2),
            "end_sec": round(t_cur + dur, 2),
            "duration_sec": round(dur, 2),
            "effect": s.get("effect", "zoom_in"),
            "text": txt,
            "asset": s.get("asset", "")
        })
        t_cur += (dur - FADE) if i < len(scenes) - 1 else dur

    (rd / "video" / "timecodes.txt").write_text("\n".join(tc_lines), encoding="utf-8")
    (rd / "video" / "timecodes.json").write_text(json.dumps(tc_items, indent=2, ensure_ascii=False), encoding="utf-8")

    return {
        "ok": True,
        "scene_index": scene_idx,
        "updated_scene": sc,
        "video_url": f"/files/runs/{run_id}/video/episode.mp4?t={int(time.time())}",
    }


@app.post("/api/storyboard/enhance_prompt")
def api_storyboard_enhance_prompt(body: dict):
    """Refines a scene visual prompt using LLM grounded in ASSET_RULES.md."""
    user_idea = (body.get("prompt") or "").strip()
    scene_text = (body.get("scene_text") or "").strip()
    preset_name = body.get("visual_preset", "dark_history_cinematic")
    from modules.m3_visual.runner import _load_visual_preset
    preset = _load_visual_preset(preset_name)

    system_prompt = (
        "You are an expert visual director for cinema-grade historical documentaries.\n"
        "Your task is to take the user's idea and scene narration, and craft a single masterwork English prompt for 35mm film photography.\n"
        "Rules:\n"
        "- Authentic archival atmosphere, chiaroscuro lighting, desaturated historical palette, gritty textures, deep dramatic volumetric shadows.\n"
        "- NO AI slop, no plastic smooth CGI, no cartoon, no collages, no multiple panels, no text.\n"
        "- Output JSON ONLY: {\"enhanced_prompt\": \"...\", \"suggested_effect\": \"zoom_in|zoom_out|pan_left_right|pan_right_left|tilt_up|tilt_down|handheld_drift|film_grain|vignette_focus|cinematic_contrast\", \"rationale\": \"...\"}\n"
    )
    user_prompt = f"Scene Narration:\n\"{scene_text}\"\n\nUser Idea/Notes:\n\"{user_idea}\"\n\nPreset Style:\n{preset.get('style_prompt', '')}"

    from core.secrets import load_env
    from core.providers import router as router_mod
    load_env_ctx()
    provs = yaml.safe_load((WORKSPACE / "config" / "providers.yaml").read_text(encoding="utf-8"))
    try:
        registry = router_mod.build_registry(provs, router_mod._resolve_secret)
        llm_default = provs.get("defaults", {}).get("llm", "openrouter")
        llm_prov = registry.get(f"llm/{llm_default}") or registry.get("llm/mock")
        res = llm_prov.execute({
            "prompt": f"{system_prompt}\n\n{user_prompt}\nOutput valid JSON ONLY:",
            "system": system_prompt,
        })
        text = res.get("text", "")
        import re
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            data = json.loads(match.group(0))
            return {"ok": True, **data}
    except Exception:
        pass

    clean_idea = user_idea or scene_text or "historical documentary scene"
    fallback_prompt = f"35mm archival photograph, {clean_idea}, {preset.get('style_prompt', '')}, dramatic chiaroscuro lighting, deep shadows, authentic texture, 8k"
    return {
        "ok": True,
        "enhanced_prompt": fallback_prompt,
        "suggested_effect": "film_grain" if any(w in clean_idea.lower() for w in ["archive", "old", "wall", "stone"]) else "zoom_in",
        "rationale": "Cinematic 35mm prompt with chiaroscuro volumetric lighting and deep shadows."
    }



from ui import api_market  # noqa: E402  (pricing/title/trend/export)
from ui import api_studio  # noqa: E402  (voices, motion, block studio)
@app.post("/api/run/{run_id}/render")
def api_run_render(run_id: str, request: "Request" = None):
    """P5 preview flow: turn a DRAFT run into the real render — strip draft
    overrides, reset m2_audio/m3_visual (their artifacts were estimates), and
    resume the pipeline with synthesis + images + assembly + metadata."""
    import shutil
    rd = runs_root() / run_id
    st = _state()
    row = st.get_run(run_id)
    if not row:
        st.close()
        return JSONResponse({"error": "run not found"}, status_code=404)
    manifest = json.loads(row["manifest"])
    overrides = manifest.get("overrides") or {}
    if not overrides.get("draft_plan"):
        st.close()
        return JSONResponse({"error": "run is not in draft state"}, status_code=400)
    overrides.pop("draft_plan", None)
    (overrides.get("visual") or {}).pop("plan_only", None)
    # keep manifest consistent in db + on disk
    st.conn.execute("UPDATE runs SET manifest=? WHERE run_id=?",
                    (json.dumps(manifest, ensure_ascii=False), run_id))
    st.conn.execute("DELETE FROM steps WHERE run_id=? AND step IN ('m2_audio','m3_visual')", (run_id,))
    st.conn.execute("UPDATE runs SET status='running' WHERE run_id=?", (run_id,))
    st.conn.commit()
    st.close()
    for sub in ("subtitles", "visual", "audio"):
        shutil.rmtree(rd / sub, ignore_errors=True)
    log = (runs_root() / f"{run_id}.ui.log").open("a", encoding="utf-8")
    from ui.server import _tenant_env
    proc = subprocess.Popen([str(PY), "-u", "-m", "core.cli", "resume", run_id],
                            stdout=log, stderr=subprocess.STDOUT, cwd=str(WORKSPACE),
                            env=_tenant_env())
    import ui.server as _srv
    _srv._procs[run_id] = proc
    return {"ok": True, "run_id": run_id, "status": "rendering"}


@app.post("/api/run/{run_id}/cancel")
def api_run_cancel(run_id: str, request: "Request" = None):
    """P5-03: cancel a queued or running run; queued/failed refunds the credit."""
    from ui.server import _run_queue, _queue_lock, _procs, tenants as _t, WORKSPACE as _WS
    user = getattr(request.state, "tenant_user", None) if request is not None else None
    with _queue_lock:
        for job in list(_run_queue):
            if job["run_id"] == run_id:
                _run_queue.remove(job)
                if user and not (user.get("role") == "admin" or user.get("unlimited")):
                    _t.refund_credit(_WS, user["id"])
                return {"ok": True, "cancelled": "queued", "refunded": True}
    proc = _procs.get(run_id)
    if proc and proc.poll() is None:
        proc.terminate()
        st = _state()
        st.set_run_status(run_id, "failed")
        st.conn.execute("UPDATE steps SET status='failed', error='cancelled by user' "
                        "WHERE run_id=? AND status IN ('running','pending')", (run_id,))
        st.conn.commit()
        st.close()
        if user and not (user.get("role") == "admin" or user.get("unlimited")):
            _t.refund_credit(_WS, user["id"])
        return {"ok": True, "cancelled": "running", "refunded": True}
    return JSONResponse({"error": "run is not active"}, status_code=404)


# --- brand kit (5b): channel identity applied to covers ----------------------

BRAND_KEYS = ("palette", "style_keywords", "channel_name", "footer_text", "cover_style")


@app.get("/api/brand_kit")
def api_brand_kit_get():
    f = config_root() / "brand_kit.yaml"
    data = yaml.safe_load(f.read_text(encoding="utf-8")) if f.exists() else {}
    return {"brand": data or {}}


@app.post("/api/brand_kit")
def api_brand_kit_save(body: dict):
    f = config_root() / "brand_kit.yaml"
    if f.exists():
        f.with_suffix(".yaml.bak").write_text(f.read_text(encoding="utf-8"), encoding="utf-8")
    clean = {k: str(body.get(k, "")).strip() for k in BRAND_KEYS if body.get(k)}
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(yaml.safe_dump(clean, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return {"ok": True, "brand": clean}


def _brand_cover_suffix() -> str:
    """Brand kit style keywords appended to cover generation prompts."""
    try:
        f = config_root() / "brand_kit.yaml"
        data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        parts = [data.get("cover_style") or "", data.get("style_keywords") or ""]
        return (", ".join(p for p in parts if p)).strip(", ")
    except Exception:  # noqa: BLE001
        return ""


# --- prompt library (5c): reusable prompts, CRUD ------------------------------

@app.get("/api/prompts")
def api_prompts_list():
    f = config_root() / "prompt_library.yaml"
    data = yaml.safe_load(f.read_text(encoding="utf-8")) if f.exists() else {}
    return {"prompts": data or {}}


@app.post("/api/prompts/save")
def api_prompts_save(body: dict):
    name = (body.get("name") or "").strip()
    text = body.get("text") or ""
    if not name:
        return JSONResponse({"error": "name required"}, status_code=400)
    f = config_root() / "prompt_library.yaml"
    data = (yaml.safe_load(f.read_text(encoding="utf-8")) or {}) if f.exists() else {}
    if body.get("delete"):
        data.pop(name, None)
    else:
        data[name] = text
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return {"ok": True, "prompts": data}


# --- watched folder (5d): drop .txt/.md -> episode auto-launch ----------------

def _watched_config():
    f = WORKSPACE / "config" / "ui_settings.yaml"
    data = yaml.safe_load(f.read_text(encoding="utf-8")) if f.exists() else {}
    return bool(data.get("watched_enabled")), str(data.get("watched_folder") or ""), \
        int(data.get("watched_max_minutes", 1) or 1)


def _watched_scan_once():
    """One scan pass: new .txt/.md files become episodes (own_script)."""
    import ui.server as _srv

    enabled, folder, minutes = _watched_config()
    if not enabled or not folder:
        return
    d = Path(folder)
    if not d.is_dir():
        return
    done = d / "_processed"
    done.mkdir(exist_ok=True)
    for f in sorted(d.glob("*.txt")) + sorted(d.glob("*.md")):
        if not f.is_file():
            continue
        target = done / f.name
        i = 1
        while target.exists():
            target = done / f"{f.stem}_{i}{f.suffix}"
            i += 1
        try:
            content = f.read_text(encoding="utf-8", errors="ignore")[:400_000]
            fake_req = type("R", (), {"state": type("S", (), {"tenant_user": None, "session_token": ""})()})()
            body = {"topic": f.stem.replace("_", " ")[:120], "target_minutes": minutes,
                    "own_script": content, "language": "ru"}
            res = api_episode(body, fake_req)
            _srv._watched_log = getattr(_srv, "_watched_log", [])
            _srv._watched_log.append({"file": f.name, "res": res})
            shutil.move(str(f), str(target))
        except Exception as e:  # noqa: BLE001 — never let a bad file kill the watcher
            _srv._watched_log = getattr(_srv, "_watched_log", [])
            _srv._watched_log.append({"file": f.name, "error": str(e)})


def _watched_watcher():
    import time as _t

    while True:
        _t.sleep(10)
        try:
            _watched_scan_once()
        except Exception:  # noqa: BLE001
            pass


@app.get("/api/watched")
def api_watched_status():
    enabled, folder, minutes = _watched_config()
    import ui.server as _srv

    return {"enabled": enabled, "folder": folder, "minutes": minutes,
            "log": (getattr(_srv, "_watched_log", []) or [])[-10:]}


@app.post("/api/watched")
def api_watched_save(body: dict):
    f = WORKSPACE / "config" / "ui_settings.yaml"
    data = yaml.safe_load(f.read_text(encoding="utf-8")) if f.exists() else {}
    data = data or {}
    if "watched_enabled" in body:
        data["watched_enabled"] = bool(body["watched_enabled"])
    if "watched_folder" in body:
        data["watched_folder"] = str(body["watched_folder"])
    if "watched_max_minutes" in body:
        data["watched_max_minutes"] = int(body["watched_max_minutes"] or 1)
    f.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    enabled, folder, minutes = _watched_config()
    return {"ok": True, "enabled": enabled, "folder": folder, "minutes": minutes}


# --- MCP one-click (5e): config snippet for Claude Desktop / ZCode ------------

@app.get("/api/mcp/config")
def api_mcp_config():
    """One-click MCP: paste the mcpServers block into the MCP client config."""
    return {"mcpServers": {"pipeline": {
        "command": str(PY),
        "args": [str(WORKSPACE / "tools" / "mcp_server.py")],
    }},
        "note": "Paste this mcpServers block into claude_desktop_config.json to give LLMs access to list_runs / run_status / create_episode tools."}


from ui import api_auth  # noqa: E402  (P5-01: sessions, register/login, admin)
