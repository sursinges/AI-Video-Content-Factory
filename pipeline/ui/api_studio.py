"""Studio APIs: voice cloning library (on-device F5-TTS, MIT), motion graphics
endpoints, block-based studio builder (forward construction: add scenes ->
TTS + image + render -> mp4)."""

import base64
import json
import time
from pathlib import Path

import yaml
from fastapi import Request
from starlette.responses import JSONResponse

from ui.server import WORKSPACE, _state, app, runs_root, data_root, config_root, load_env_ctx

def _voices_path():
    return data_root() / "data" / "voices.json"


def _voice_clone_blocked(request=None):
    """Voice cloning runs on the host GPU — disabled for hosted users (owner:
    the tab stays closed on servers until GPU capacity exists)."""
    import ui.server as _srv
    if _srv.tenants.hosted_mode(_srv.WORKSPACE):
        user = getattr(request.state, "tenant_user", None) if request is not None else None
        if not user or user.get("role") != "admin":
            return True
    return False


def _voices() -> dict:
    vp = _voices_path()
    if vp.exists():
        return json.loads(vp.read_text(encoding="utf-8"))
    return {"voices": []}


def _save_voices(d: dict):
    vp = _voices_path()
    vp.parent.mkdir(parents=True, exist_ok=True)
    vp.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


# --- voice library (on-device cloning via F5-TTS, MIT license) ----------------

@app.get("/api/voices")
def api_voices():
    return _voices()


@app.post("/api/voices/add")
def api_voices_add(body: dict, request: "Request" = None):
    if _voice_clone_blocked(request):
        return JSONResponse({"error": "voice cloning is coming soon (hosted)", "soon": True}, status_code=403)
    d = _voices()
    vid = (body.get("id") or "voice").strip().replace(" ", "_")
    b64 = body.get("audio_b64", "")
    if b64:
        raw = base64.b64decode(b64.split(",")[-1])
        vp = WORKSPACE / "models" / "voices"
        vp.mkdir(parents=True, exist_ok=True)
        (vp / f"{vid}.wav").write_bytes(raw)
    d["voices"].append({
        "id": vid, "name": body.get("name", vid),
        "engine": body.get("engine", "f5_ru"),
        "ref_audio": body.get("ref_audio") or str(WORKSPACE / "models" / "voices" / f"{vid}.wav"),
        "ref_text": body.get("ref_text", ""),
    })
    _save_voices(d)
    return {"ok": True}


@app.post("/api/voices/delete")
def api_voices_delete(body: dict, request: "Request" = None):
    if _voice_clone_blocked(request):
        return JSONResponse({"error": "voice cloning is coming soon (hosted)", "soon": True}, status_code=403)
    d = _voices()
    d["voices"] = [v for v in d["voices"] if v["id"] != body.get("id")]
    _save_voices(d)
    return {"ok": True}


@app.post("/api/voices/preview")
def api_voices_preview(body: dict, request: "Request" = None):
    if _voice_clone_blocked(request):
        return JSONResponse({"error": "voice cloning is coming soon (hosted)", "soon": True}, status_code=403)
    voice = next((v for v in _voices()["voices"] if v["id"] == body.get("id")), None)
    if not voice:
        return JSONResponse({"error": "голос не найден"}, status_code=404)
    st = _state()
    provs = yaml.safe_load((config_root() / "providers.yaml").read_text(encoding="utf-8"))
    from core.providers import router as router_mod

    load_env_ctx()
    registry = router_mod.build_registry(provs, router_mod._resolve_secret)
    engine = registry.get("tts/" + voice.get("engine", "f5_ru"))
    if engine is None:
        st.close()
        return JSONResponse({"error": "движок " + voice.get("engine", "") + " не настроен"}, status_code=400)
    out = runs_root() / "_voices" / f"{voice['id']}.mp3"
    try:
        engine.execute({
            "text": body.get("text") or "Привет. Так звучит мой клонированный голос в пайплайне.",
            "out_path": str(out), "language": body.get("language", "ru"),
            "ref_audio": voice["ref_audio"], "ref_text": voice["ref_text"]})
        st.close()
        return {"ok": True, "path": str(out)}
    except Exception as e:  # noqa: BLE001
        st.close()
        return JSONResponse({"error": str(e)[:250]}, status_code=502)


# --- generic asset upload (studio scenes, references) ---------------------------

@app.post("/api/upload_asset")
def api_upload_asset(body: dict):
    b64 = body.get("b64", "")
    name = (body.get("name") or "asset.bin").strip()
    safe = "".join(c for c in name if c.isalnum() or c in "._- ") or "asset"
    if not b64:
        return JSONResponse({"error": "пустой файл"}, status_code=400)
    try:
        raw = base64.b64decode(b64.split(",")[-1], validate=False)
    except Exception:
        return JSONResponse({"error": "невалидные данные файла"}, status_code=400)
    if len(raw) > 25 * 1024 * 1024:
        return JSONResponse({"error": "файл больше 25 МБ"}, status_code=400)
    from ui.server import _tenant_over_quota
    if _tenant_over_quota():
        return JSONResponse({"error": "disk quota exceeded — contact the administrator"}, status_code=507)
    dir_name = body.get("dir")
    if dir_name == "music":
        folder = WORKSPACE / "models" / "music"
    else:
        folder = runs_root() / (dir_name if dir_name in ("references",) else "_uploads")
    folder.mkdir(parents=True, exist_ok=True)
    out = folder / safe
    i = 1
    while out.exists():
        out = folder / f"{out.stem}_{i}{out.suffix}"
        i += 1
    out.write_bytes(raw)
    return {"ok": True, "path": str(out)}


# --- formats CRUD ----------------------------------------------------------------

@app.post("/api/formats/save")
def api_formats_save(body: dict):
    key = (body.get("key") or "").strip().replace(" ", "_")
    preset = body.get("preset")
    if not key or not isinstance(preset, dict):
        return JSONResponse({"error": "нужны key и preset"}, status_code=400)
    fpath = config_root() / "formats.yaml"
    from ui.server import _backup

    _backup(fpath)
    data = yaml.safe_load(fpath.read_text(encoding="utf-8")) or {}
    data[key] = preset
    fpath.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return {"ok": True}


# --- motion graphics ------------------------------------------------------------

@app.get("/api/motion/list")
def api_motion_list():
    from core import motion

    return {"projects": motion.list_projects(), "templates": motion.list_templates(),
            "aspects": list(motion.ASPECTS.keys())}


@app.post("/api/motion/create")
def api_motion_create(body: dict):
    from core import motion

    try:
        return {"ok": True, **motion.create_project(
            body.get("name", "motion"), body.get("template", "kinetic_title"),
            body.get("params", {}), aspect=body.get("aspect", "16:9"))}
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": str(e)}, status_code=400)


@app.post("/api/motion/render")
def api_motion_render(body: dict):
    from core import motion

    try:
        res = motion.render(body.get("project", ""), audio_path=body.get("audio_path"))
        return {"ok": True, **res}
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"error": str(e)[:250]}, status_code=502)


# --- block studio: forward construction ----------------------------------------

@app.post("/api/studio/build")
def api_studio_build(body: dict):
    """Forward construction: user composes scenes (text + image/prompt + effect),
    we TTS each, generate images where asked, render motion, concat, mux."""
    scenes = body.get("scenes") or []
    if not scenes:
        return JSONResponse({"error": "пустой список сцен"}, status_code=400)
    num = 1
    for p in (runs_root()).glob("studio-*.manifest.yaml"):
        try:
            num = max(num, int(p.name.split("-")[2].split(".")[0]) + 1)
        except (ValueError, IndexError):
            pass
    run_id = f"studio-{num:04d}"
    run_dir = runs_root() / run_id
    (run_dir / "scenes").mkdir(parents=True, exist_ok=True)

    st = _state()
    provs = yaml.safe_load((config_root() / "providers.yaml").read_text(encoding="utf-8"))
    from core.providers import router as router_mod

    load_env_ctx()
    router = router_mod.Router(provs, st, run_id, run_dir)
    fmt = yaml.safe_load((config_root() / "formats.yaml").read_text(encoding="utf-8"))
    from core.media import concat_audio, concat_video, ffprobe_duration, render_scene_clip
    import soundfile as sf

    voice_override = body.get("voice") or {}
    scene_files, timeline = [], []
    for i, sc in enumerate(scenes):
        text = (sc.get("text") or "").strip()
        dur = float(sc.get("duration") or 0)
        # 1) narration
        if text:
            audio = run_dir / "scenes" / f"s{i:02d}.mp3"
            payload = {"text": text, "out_path": str(audio), "format": "mp3",
                       "language": body.get("language", "ru")}
            payload.update({k: voice_override[k] for k in ("ref_audio", "ref_text") if voice_override.get(k)})
            res = router.call("tts", payload)
            try:
                dur = sf.info(res["audio_path"]).duration
            except Exception:  # noqa: BLE001
                dur = dur or 4.0
        dur = max(dur, 1.5)
        # 2) image (upload path or generate)
        img = sc.get("image_path")
        if img and not Path(img).exists():
            img = None
        if not img:
            prompt = sc.get("prompt") or "flat vector night scene, calm sleep mood, no text"
            out_img = run_dir / "scenes" / f"s{i:02d}.png"
            try:
                res = router.call("image", {"prompt": prompt, "out_path": str(out_img),
                                            "width": 1280, "height": 720})
                img = res["image_path"]
            except Exception:  # noqa: BLE001 — image optional, text-only scene ok
                img = None
        # 3) motion clip (image optional: audio-only scene gets black)
        clip = run_dir / "scenes" / f"s{i:02d}.mp4"
        if img:
            render_scene_clip(img, clip, duration=dur, effect=sc.get("effect") or "zoom_in")
        else:
            ff = __import__("core.media", fromlist=["ff"]).ff
            ff(["-f", "lavfi", "-i", f"color=c=#0e0f10:s=1920x1080:d={dur:.2f}",
                "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p", str(clip)])
        scene_files.append(clip)
        timeline.append({"scene": i + 1, "text": text[:120], "image": img,
                         "duration": round(dur, 2), "effect": sc.get("effect")})
    # 4) concat + music
    from core.media import concat_audio, mix_and_master, mux

    silent = run_dir / "video_silent.mp4"
    concat_video(scene_files, silent)
    total = sum(t["duration"] for t in timeline)
    amb = run_dir / "ambient.m4a"
    try:
        router.call("music", {"out_path": str(amb), "duration_sec": total,
                              "mood": body.get("music_mood", "calm ambient night")})
        mix_src, mix = None, run_dir / "final.mp4"
        voice = run_dir / "voice.wav"
        concat_audio([s for s in scene_files], voice)
        mix_and_master(voice, amb, run_dir / "audio.m4a")
        mux(silent, run_dir / "audio.m4a", run_dir / "final.mp4")
    except Exception:  # noqa: BLE001 — music optional
        import shutil

        shutil.copy(silent, run_dir / "final.mp4")
    st.close()
    (run_dir / "timeline.json").write_text(
        json.dumps({"run_id": run_id, "timeline": timeline, "total_sec": round(total, 2)},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "run_id": run_id, "video": str(run_dir / "final.mp4"),
            "total_sec": round(total, 2), "timeline": timeline}
