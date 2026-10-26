"""Motion Graphics engine (ViralMint HyperFrames-inspired, own implementation).

A composition = an HTML file that defines window.renderFrame(t) — a pure JS
function that positions every element for time t (seconds). The renderer:
  1. loads the file in Playwright (local Chromium),
  2. for each frame t calls renderFrame(t) and screenshots,
  3. assembles PNG frames -> mp4 via ffmpeg (narration mux optional).
Deterministic, free, runs locally. Templates live in motion_templates/.
"""

import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECTS = ROOT / "runs" / "motion"
TEMPLATES = ROOT / "motion_templates"


def list_projects() -> list[dict]:
    if not PROJECTS.exists():
        return []
    out = []
    for f in sorted(PROJECTS.glob("*/composition.html")):
        cfg = f.parent / "config.json"
        meta = json.loads(cfg.read_text(encoding="utf-8")) if cfg.exists() else {}
        out.append({"id": f.parent.name, **meta})
    return out


def list_templates() -> list[str]:
    if not TEMPLATES.exists():
        return []
    return sorted(f.stem for f in TEMPLATES.glob("*.html"))


ASPECTS = {
    "16:9": (1920, 1080),   # горизонт — YouTube
    "9:16": (1080, 1920),   # вертикаль — Shorts/Reels/TikTok
    "1:1": (1080, 1080),    # квадрат — посты
}


def create_project(name: str, template: str, params: dict, aspect: str = "16:9") -> dict:
    tpl = TEMPLATES / f"{template}.html"
    if not tpl.exists():
        raise ValueError(f"шаблон '{template}' не найден: {list_templates()}")
    if aspect not in ASPECTS:
        aspect = "16:9"
    safe = "".join(c for c in name if c.isalnum() or c in "-_") or "motion"
    folder = PROJECTS / f"{int(time.time())}-{safe}"
    folder.mkdir(parents=True, exist_ok=True)
    html = tpl.read_text(encoding="utf-8")
    for k, v in (params or {}).items():
        html = html.replace("{{" + k.upper() + "}}", str(v))
    (folder / "composition.html").write_text(html, encoding="utf-8")
    meta = {"name": name, "template": template, "params": params or {},
            "aspect": aspect, "duration": float((params or {}).get("DURATION", 5))}
    (folder / "config.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"id": folder.name, "path": str(folder), **meta}


def render(project_id: str, fps: int = 25, audio_path: str | None = None) -> dict:
    folder = PROJECTS / project_id
    html = folder / "composition.html"
    if not html.exists():
        raise ValueError("проект не найден")
    cfg = json.loads((folder / "config.json").read_text(encoding="utf-8"))
    duration = float(cfg.get("duration", 5))
    w, h = ASPECTS.get(cfg.get("aspect", "16:9"), ASPECTS["16:9"])
    frames_dir = folder / "frames"
    shutil.rmtree(frames_dir, ignore_errors=True)
    frames_dir.mkdir(parents=True, exist_ok=True)

    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": w, "height": h})
        page.goto(html.as_uri(), wait_until="load")
        page.wait_for_timeout(500)
        n_frames = int(duration * fps)
        for i in range(n_frames):
            t = i / fps
            page.evaluate(f"renderFrame({t:.4f})")
            page.screenshot(path=str(frames_dir / f"{i:05d}.png"),
                            clip={"x": 0, "y": 0, "width": w, "height": h})
        browser.close()

    out = folder / "motion.mp4"
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-framerate", str(fps), "-i", str(frames_dir / "%05d.png"),
         "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
         *(["-i", audio_path, "-map", "0:v", "-map", "1:a", "-c:a", "aac", "-shortest"] if audio_path else []),
         str(out)],
        check=True, capture_output=True, text=True)
    shutil.rmtree(frames_dir, ignore_errors=True)
    return {"video": str(out), "duration_sec": duration, "fps": fps}


import time  # noqa: E402
