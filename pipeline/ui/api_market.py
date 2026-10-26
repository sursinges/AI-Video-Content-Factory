"""Extra API part 2 (competitor-inspired features): pricing estimate,
title analyzer, trend scout (official YouTube API only), settings export/import.
Imported at the end of ui/api_extra.py."""

import json
import time
from pathlib import Path

import yaml
from starlette.responses import JSONResponse

from ui.server import WORKSPACE, _state, _library, app, runs_root, data_root, config_root, load_env_ctx


@app.get("/api/formats")
def api_formats():
    f = config_root() / "formats.yaml"
    return yaml.safe_load(f.read_text(encoding="utf-8")) or {}


@app.get("/api/music/moods")
def api_music_moods():
    """Mood list + local library tracks (models/music/) for the music picker."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "music_manager", WORKSPACE / "tools" / "music_library" / "manager.py")
    mgr = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mgr)
    folder = WORKSPACE / "models" / "music"
    tracks = []
    if folder.exists():
        mgr.scan(str(folder))
        if mgr.INDEX.exists():
            tracks = json.loads(mgr.INDEX.read_text(encoding="utf-8")).get("tracks", [])
    from core.providers.ambient_synth import MOODS

    return {"moods": MOODS, "tracks": tracks}


@app.get("/api/music/preview")
def api_music_preview(mood: str = "night"):
    """Synthesize a 10 s ambient preview for the mood picker."""
    from core.media import ff
    from core.providers.ambient_synth import MOODS, _synth_filtergraph

    if mood not in MOODS:
        return JSONResponse({"error": "unknown mood"}, status_code=400)
    out = runs_root() / "_test" / f"ambient_{mood}.mp3"
    out.parent.mkdir(parents=True, exist_ok=True)
    ins, fc = _synth_filtergraph(mood, 10)
    ff(["-y", *ins, "-filter_complex", fc, "-map", "[aout]",
        "-c:a", "libmp3lame", "-b:a", "96k", str(out)])
    return {"ok": True, "url": f"/files/runs/_test/ambient_{mood}.mp3?t={int(time.time())}"}


@app.get("/api/scheduled")
def api_scheduled():
    """Runs with a publish_at override — planned YouTube releases."""
    out = []
    for mf in (runs_root()).glob("*.manifest.yaml"):
        try:
            man = yaml.safe_load(mf.read_text(encoding="utf-8")) or {}
        except Exception:  # noqa: BLE001
            continue
        ov = man.get("overrides") or {}
        pa = ov.get("publish_at")
        if not pa:
            continue
        rid = mf.name.replace(".manifest.yaml", "")
        out.append({"run_id": rid, "publish_at": str(pa),
                    "visibility": str(ov.get("publish_visibility") or "private"),
                    "title": str(man.get("topic") or rid)[:80]})
    out.sort(key=lambda x: x["publish_at"])
    return {"scheduled": out}


@app.get("/api/search")
def api_search(q: str = ""):
    """Global search: episodes + topics + notes (label matches and content hits)."""
    q = (q or "").strip().lower()
    if len(q) < 2:
        return {"results": []}
    out = []
    st = _state()
    for r in st.list_runs():
        try:
            man = json.loads(r["manifest"]) if r["manifest"] else {}
        except Exception:  # noqa: BLE001
            man = {}
        title = str(man.get("topic") or r["run_id"])
        if q in (title + " " + r["run_id"]).lower():
            out.append({"type": "episode", "id": r["run_id"], "label": title[:70]})
    st.close()
    lib = _library()
    try:
        for t in lib.conn.execute("SELECT id, title FROM topics ORDER BY id DESC LIMIT 500"):
            if q in str(t["title"]).lower():
                out.append({"type": "topic", "id": t["id"], "label": str(t["title"])[:70]})
    finally:
        lib.close()
    import sys as _sys

    _sys.path.insert(0, str(WORKSPACE / "tools" / "notes"))
    import manager as notes_mgr

    for f in notes_mgr.list_notes():
        if q in f.lower():
            out.append({"type": "note", "id": f, "label": f})
            continue
        try:
            content = notes_mgr.read(f)
        except Exception:  # noqa: BLE001
            continue
        pos = content.lower().find(q)
        if pos >= 0:
            out.append({"type": "note", "id": f, "label": f,
                        "snippet": content[max(0, pos - 30):pos + 60].replace("\n", " ")})
    return {"results": out[:25]}


@app.get("/api/system")
def api_system():
    """System & storage snapshot: versions, disk usage, LLM cache stats."""
    import os
    import platform
    import subprocess as sp

    out = {"app": "pipeline MONOLITH", "python": platform.python_version()}
    try:
        r = sp.run(["ffmpeg", "-version"], capture_output=True, text=True, timeout=10)
        out["ffmpeg"] = (r.stdout or "").splitlines()[0][:90] if r.returncode == 0 else "not found"
    except Exception:
        out["ffmpeg"] = "not found"

    def dir_size(p: Path) -> int:
        total = 0
        for root, _dirs, files in os.walk(p):
            for fn in files:
                try:
                    total += os.path.getsize(os.path.join(root, fn))
                except OSError:
                    pass
        return total

    runs_dir = runs_root()
    out["runs_size"] = dir_size(runs_dir) if runs_dir.exists() else 0
    out["runs_count"] = sum(1 for d in runs_dir.iterdir() if d.is_dir()) if runs_dir.exists() else 0
    st = _state()
    row = st.conn.execute(
        "SELECT COUNT(*) AS c, COALESCE(SUM(LENGTH(response)),0) AS s FROM cache").fetchone()
    out["cache_entries"], out["cache_bytes"] = row["c"], row["s"]
    st.close()
    return out


@app.post("/api/system/clear_cache")
def api_system_clear_cache():
    """Drop the LLM/provider response cache (regeneratable — runs/videos untouched)."""
    st = _state()
    n = st.conn.execute("SELECT COUNT(*) AS c FROM cache").fetchone()["c"]
    st.conn.execute("DELETE FROM cache")
    st.conn.commit()
    st.close()
    return {"ok": True, "cleared": n}


@app.get("/api/spend/summary")
def api_spend_summary():
    """GAP-05: канал за 30 дней и за всё время — выпуски, минуты, токены, расход,
    цена минуты и топ-5 самых дорогих прогонов (задел под hosted-биллинг)."""
    from datetime import datetime, timedelta
    st = _state()

    def agg(where: str) -> dict:
        row = st.conn.execute(
            f"SELECT COUNT(*) AS calls, COALESCE(SUM(tokens),0) AS tokens, "
            f"COALESCE(SUM(cost_usd),0) AS cost FROM usage {where}").fetchone()
        return {"calls": row["calls"], "tokens": row["tokens"], "cost": round(row["cost"], 4)}

    out = {"month": agg("WHERE created_at >= datetime('now', '-30 days')"), "all": agg("")}
    top_rows = st.conn.execute(
        "SELECT run_id, COUNT(*) AS calls, COALESCE(SUM(tokens),0) AS tokens, "
        "COALESCE(SUM(cost_usd),0) AS cost FROM usage "
        "GROUP BY run_id ORDER BY cost DESC LIMIT 5").fetchall()
    runs = st.conn.execute("SELECT manifest, status, created_at FROM runs").fetchall()
    st.close()
    out["top"] = [{"run_id": r["run_id"], "calls": r["calls"], "tokens": r["tokens"],
                   "cost": round(r["cost"], 4)} for r in top_rows]

    cutoff = (datetime.utcnow() - timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
    done_m = done_a = 0
    minutes_m = minutes_a = 0.0
    for r in runs:
        try:
            m = json.loads(r["manifest"])
        except Exception:  # noqa: BLE001
            m = {}
        mins = float(m.get("target_minutes") or 0)
        if r["status"] != "done":
            continue
        done_a += 1
        minutes_a += mins
        if (r["created_at"] or "") >= cutoff:
            done_m += 1
            minutes_m += mins
    out["month"]["episodes"] = done_m
    out["month"]["minutes"] = round(minutes_m, 1)
    out["all"]["episodes"] = done_a
    out["all"]["minutes"] = round(minutes_a, 1)
    for k in ("month", "all"):
        mins = out[k]["minutes"]
        out[k]["usd_per_minute"] = round(out[k]["cost"] / mins, 4) if mins > 0 else None
    return out


@app.post("/api/profiles/activate")
def api_profiles_activate(body: dict):
    """GAP-04: switch the active channel profile — copies profiles/<name>.yaml
    over config/channel.profile.yaml (a .bak of the previous profile is kept)."""
    name = (body.get("name") or "").strip()
    if not name.replace("_", "").replace("-", "").isalnum():
        return JSONResponse({"error": "invalid profile name: use letters, numbers, _, -"}, status_code=400)
    src = config_root() / "profiles" / f"{name}.yaml"
    if not src.exists():
        return JSONResponse({"error": "profile not found"}, status_code=404)
    dst = config_root() / "channel.profile.yaml"
    dst.with_suffix(".yaml.bak").write_text(dst.read_text(encoding="utf-8"), encoding="utf-8")
    dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    return {"ok": True, "name": name}


VISUAL_PRESETS_FILE = WORKSPACE / "config" / "visual_presets.yaml"  # host defaults
VISUAL_PRESETS_CUSTOM = WORKSPACE / "config" / "visual_presets_custom.yaml"


def _visual_presets_merged() -> dict:
    """Main presets + user-created/overridden ones (custom file never touches the main YAML)."""
    data = {}
    if VISUAL_PRESETS_FILE.exists():
        data = yaml.safe_load(VISUAL_PRESETS_FILE.read_text(encoding="utf-8")) or {}
    # per-tenant custom overlay lives in the tenant config (P5-02)
    global VISUAL_PRESETS_CUSTOM
    VISUAL_PRESETS_CUSTOM = data_root() / "config" / "visual_presets_custom.yaml"
    custom = {}
    if VISUAL_PRESETS_CUSTOM.exists():
        custom = yaml.safe_load(VISUAL_PRESETS_CUSTOM.read_text(encoding="utf-8")) or {}
    merged = {"default_preset": data.get("default_preset", "dark_history_cinematic")}
    presets = dict(data.get("presets") or {})
    presets.update(custom.get("presets") or {})
    merged["presets"] = presets
    return merged


@app.get("/api/visual_presets")
def api_visual_presets():
    return _visual_presets_merged()


@app.post("/api/visual_presets/save")
def api_visual_presets_save(body: dict):
    key = (body.get("key") or "").strip()
    if not key.replace("_", "").replace("-", "").isalnum():
        return JSONResponse({"error": "invalid preset key: use letters, numbers, _, -"}, status_code=400)
    custom = {"presets": {}}
    if VISUAL_PRESETS_CUSTOM.exists():
        custom = yaml.safe_load(VISUAL_PRESETS_CUSTOM.read_text(encoding="utf-8")) or {"presets": {}}
    custom.setdefault("presets", {})[key] = body.get("preset") or {}
    VISUAL_PRESETS_CUSTOM.write_text(yaml.safe_dump(custom, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return {"ok": True}


@app.get("/api/provider_catalog")
def api_provider_catalog():
    cat = yaml.safe_load((WORKSPACE / "config" / "provider_catalog.yaml").read_text(encoding="utf-8")) or {}
    import os

    out = []
    for item in cat.get("catalog", []):
        has_key = bool(item.get("key_ref")) and item["key_ref"] in os.environ
        out.append({**item, "connected": has_key})
    return {"catalog": out}


@app.post("/api/catalog/setup")
def api_catalog_setup(body: dict):
    """One-click provider setup from the catalog: save key + register provider
    + optional make-default. Reuses envstore and providers.yaml flow."""
    from core.envstore import save_key

    item = body.get("item") or {}
    pid = (body.get("id") or "").strip()
    key = (body.get("key") or "").strip()
    if not pid:
        return JSONResponse({"error": "id required"}, status_code=400)
    cat = yaml.safe_load((WORKSPACE / "config" / "provider_catalog.yaml").read_text(encoding="utf-8")) or {}
    meta = next((c for c in cat.get("catalog", []) if c["id"] == pid), None)
    if meta is None:
        return JSONResponse({"error": "not found in catalog"}, status_code=404)
    if meta.get("key_ref") and key:
        from core import tenants as _t
        save_key(_t.secrets_env(WORKSPACE), meta["key_ref"], key)
    if meta.get("base_url"):
        provs_path = config_root() / "providers.yaml"
        provs_path.with_suffix(".yaml.bak").write_text(provs_path.read_text(encoding="utf-8"), encoding="utf-8")
        provs = yaml.safe_load(provs_path.read_text(encoding="utf-8"))
        provs["providers"] = provs.get("providers") or {}
        entry = {"type": meta["type"], "adapter": meta.get("adapter", "openai_compatible")}
        if meta.get("base_url"):
            entry["base_url"] = meta["base_url"]
        if meta.get("default_model"):
            entry["model"] = meta["default_model"]
        if meta.get("key_ref"):
            entry["api_key_ref"] = meta["key_ref"]
        if body.get("make_default"):
            provs["defaults"] = {**(provs.get("defaults") or {}), meta["type"]: pid}
        provs["providers"][pid] = entry
        provs_path.write_text(yaml.safe_dump(provs, allow_unicode=True, sort_keys=False), encoding="utf-8")
    from core.secrets import load_env

    load_env_ctx()
    return {"ok": True}

# --- pricing estimate ---------------------------------------------------------

@app.get("/api/estimate")
def api_estimate(minutes: int = 5):
    """Pre-run cost estimate (ViralMint/OpenShorts priced-card style)."""
    pricing = WORKSPACE / "config" / "pricing.yaml"
    if not pricing.exists():
        return {"usd": 0.0, "breakdown": {}, "note": "config/pricing.yaml missing — all free/local"}
    pr = yaml.safe_load(pricing.read_text(encoding="utf-8")) or {}
    chars = minutes * 1450
    llm_tokens = int(chars / 3 * 6)  # skeleton+chunks+critic+factcheck ~= 6 passes
    b = {}
    llm_p = pr.get("llm", {})
    b["llm"] = round(llm_tokens / 1e6 * llm_p.get("usd_per_1m_tokens", 0), 4)
    tts_p = pr.get("tts", {})
    b["tts"] = round(chars / 1e3 * tts_p.get("usd_per_1k_chars", 0), 4)
    img_p = pr.get("image", {})
    n_images = max(2, int(minutes * 60 / 45))
    b["image"] = round(n_images * img_p.get("usd_per_image", 0), 4)
    return {"usd": round(sum(b.values()), 4), "breakdown": b,
            "minutes": minutes, "chars": chars}


# --- title analyzer (OpenShorts-style) ----------------------------------------

@app.post("/api/title/analyze")
def api_title_analyze(body: dict):
    title = (body.get("title") or "").strip()
    topic = (body.get("topic") or "").strip()
    if len(title) < 5 and len(topic) < 5:
        return JSONResponse({"error": "title or topic required"}, status_code=400)
    st = _state()
    provs = yaml.safe_load((config_root() / "providers.yaml").read_text(encoding="utf-8"))
    from core.providers.router import Router

    router = Router(provs, st, "title", runs_root() / "_title")
    nl = chr(10)
    prompt = ("You are a YouTube video strategist and title optimizer." + nl
              + "Evaluate this video title for audience appeal, clarity, click-through potential without deceptive clickbait, 50-70 chars." + nl
              + "TITLE: " + (title or "(none)") + nl
              + "TOPIC: " + (topic or "(none)") + nl + nl
              + 'Respond strictly in JSON format: {"score": 1-10, "issues": ["..."], '
              + '"alternatives": ["option 1", "option 2", "option 3"]}')
    try:
        resp = router.call("llm", {"prompt": prompt, "temperature": 0.3})
        from modules.m1_script.prompts import extract_json

        data = extract_json(resp.get("text", ""))
        st.close()
        if not data:
            return JSONResponse({"error": "LLM returned non-JSON output"}, status_code=502)
        return {"ok": True, **data}
    except Exception as e:  # noqa: BLE001
        st.close()
        return JSONResponse({"error": str(e)[:200]}, status_code=502)


# --- trend scout: official YouTube Data API v3 ONLY (core stays clean) --------

@app.get("/api/trend/scout")
def api_trend_scout(niche: str, max_results: int = 15):
    key = ""
    envf = WORKSPACE / ".env"
    if envf.exists():
        for line in envf.read_text(encoding="utf-8").splitlines():
            if line.startswith("YOUTUBE_API_KEY="):
                key = line.split("=", 1)[1].strip()
    if not key:
        return JSONResponse({"error": "official YOUTUBE_API_KEY required in .env "
                             "(console.cloud.google.com -> YouTube Data API v3, 10k free daily quota). "
                             "Scraping is prohibited in core platform architecture."}, status_code=400)
    import httpx

    try:
        with httpx.Client(timeout=30) as client:
            r = client.get("https://www.googleapis.com/youtube/v3/search", params={
                "key": key, "part": "snippet", "q": niche, "type": "video",
                "order": "viewCount", "publishedAfter": "2026-06-01T00:00:00Z",
                "maxResults": min(max_results, 25)})
            r.raise_for_status()
            ids = [it["id"]["videoId"] for it in r.json().get("items", [])]
            stats = {}
            if ids:
                r2 = client.get("https://www.googleapis.com/youtube/v3/videos", params={
                    "key": key, "part": "statistics,snippet", "id": ",".join(ids)})
                for v in r2.json().get("items", []):
                    st = v.get("statistics", {})
                    stats[v["id"]] = {
                        "title": v["snippet"]["title"], "channel": v["snippet"]["channelTitle"],
                        "views": int(st.get("viewCount", 0)),
                        "published": v["snippet"]["publishedAt"][:10],
                        "url": "https://youtube.com/watch?v=" + v["id"]}
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": "YouTube API: " + str(e)[:200]}, status_code=502)
    now = time.time()
    out = []
    for v in stats.values():
        try:
            days = max((now - time.mktime(time.strptime(v["published"], "%Y-%m-%d"))) / 86400, 1)
        except ValueError:
            days = 30
        v["views_per_day"] = int(v["views"] / days)
        out.append(v)
    out.sort(key=lambda v: -v["views_per_day"])
    return {"ok": True, "niche": niche, "videos": out,
            "note": "scoring: views/day (view velocity). Official API, zero scraping."}


# --- settings export / import (MoneyPrinterTurbo-style) ------------------------

@app.get("/api/settings_export")
def api_settings_export():
    from core import tenants as _t
    prof = (config_root() / "channel.profile.yaml").read_text(encoding="utf-8")
    provs = (config_root() / "providers.yaml").read_text(encoding="utf-8")
    # ui_settings is the HOST file (flags/cookies) — never exported to tenants
    is_owner = not _t.current_tenant()
    ui_f = WORKSPACE / "config" / "ui_settings.yaml"
    ui_s = (ui_f.read_text(encoding="utf-8") if ui_f.exists() else "") if is_owner else ""
    return {"channel_profile": prof, "providers": provs, "ui_settings": ui_s,
            "exported_at": time.strftime("%Y-%m-%d %H:%M")}


@app.post("/api/settings_import")
def api_settings_import(body: dict):
    for name, fname in (("channel_profile", "channel.profile.yaml"),
                        ("providers", "providers.yaml"), ("ui_settings", "ui_settings.yaml")):
        text = body.get(name)
        if not text:
            continue
        try:
            if not isinstance(yaml.safe_load(text), dict):
                raise ValueError(name + ": root node must be a dict")
        except Exception as e:  # noqa: BLE001
            return JSONResponse({"error": str(e)}, status_code=400)
        if fname == "ui_settings.yaml" and _t.current_tenant():
            continue  # tenants may not touch host flags
        target = config_root() / fname
        if fname == "ui_settings.yaml":
            target = WORKSPACE / "config" / "ui_settings.yaml"
        target.with_suffix(".yaml.bak").write_text(target.read_text(encoding="utf-8"), encoding="utf-8")
        target.write_text(text, encoding="utf-8")
    return {"ok": True, "note": "backups (.yaml.bak) created"}
