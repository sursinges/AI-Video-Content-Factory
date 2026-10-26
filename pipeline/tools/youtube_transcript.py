"""YouTube link -> transcript (external add-on, not a conveyor module).

Usage:
    python tools/youtube_transcript.py <URL> [--lang ru]

Pipeline: yt-dlp tries manual/auto subtitles first (fast, exact); if none,
downloads audio and transcribes locally with faster-whisper. Result: a
markdown file in transcripts/ + a reference row in library.db so episodes
can be built from the material.

LEGAL: transcripts are for research/reference only — build your own scripts
from the IDEAS; republishing someone's text verbatim is a copyright/YPP risk.
"""

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OUT_DIR = ROOT / "transcripts"


EXTRA = []  # filled from CLI: cookies/proxy flags for yt-dlp


def run(cmd: list[str], **kw):
    if cmd[0] == "yt-dlp":
        cmd = cmd[:1] + EXTRA + cmd[1:]
    proc = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if proc.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd[:2])} failed: {proc.stderr[-400:]}")
    return proc.stdout


def video_meta(url: str) -> dict:
    out = run(["yt-dlp", "-J", "--no-playlist", url])
    return json.loads(out)


def download_subtitles(url: str, lang: str, dest: Path) -> Path | None:
    """Try manual subs, then auto subs; return the vtt path or None."""
    for args in (["--write-subs", "--sub-langs", f"{lang}.*,{lang}"],
                 ["--write-auto-subs", "--sub-langs", f"{lang}.*,{lang}"]):
        try:
            run(["yt-dlp", "--skip-download", "--no-playlist", *args,
                 "-o", str(dest / "sub"), url])
        except RuntimeError:
            continue
        vtts = list(dest.glob("sub*.vtt"))
        if vtts:
            return vtts[0]
    return None


def parse_vtt(path: Path) -> str:
    lines = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if ("-->" in line or line.startswith(("WEBVTT", "Kind:", "Language:", "NOTE"))
                or not line.strip() or re.fullmatch(r"[\d\s:.,-]+", line)):
            continue
        text = re.sub(r"<[^>]+>", "", line).strip()
        if text and text != (lines[-1] if lines else None):
            lines.append(text)
    return " ".join(lines)


def download_audio(url: str, dest: Path) -> Path:
    run(["yt-dlp", "-x", "--audio-format", "mp3", "--no-playlist",
         "-o", str(dest / "audio.%(ext)s"), url])
    return dest / "audio.mp3"


def whisper_transcribe(audio: Path, language: str) -> str:
    from faster_whisper import WhisperModel

    model = WhisperModel("small", device="cpu", compute_type="int8")
    segments, _ = model.transcribe(str(audio), language=language)
    return " ".join(s.text.strip() for s in segments)


def save_to_library(video_id: str, url: str, title: str, transcript_path: Path):
    try:
        from core.state import LibraryDB

        lib = LibraryDB(ROOT / "data" / "library.db")
        lib.conn.execute(
            'INSERT INTO "references" (channel_id, kind, path, notes) VALUES (?, ?, ?, ?)',
            ("my_channel", "video", str(transcript_path), f"YouTube {video_id}: {title} ({url})"))
        lib.conn.commit()
        lib.close()
    except Exception as e:  # noqa: BLE001 — library must not break the tool
        print(f"[warn] library save skipped: {e}")




def browser_transcript(url: str, headless: bool = True) -> str:
    """Last-resort: real browser (uses Windows system proxy, so VPN routing
    works exactly like in the user's Chrome). Opens the video, dismisses the
    consent dialog, opens the transcript panel, scrapes its text."""
    from playwright.sync_api import sync_playwright

    profile = ROOT / "runs" / "yt_profile"
    profile.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        ctx = pw.chromium.launch_persistent_context(
            str(profile), headless=headless, viewport={"width": 1400, "height": 900})
        page = ctx.new_page()
        page.goto(url, timeout=90000, wait_until="domcontentloaded")
        page.wait_for_timeout(4000)
        # consent dialog (any locale): remove backdrop + click accept
        page.evaluate("""() => {
            document.querySelectorAll('tp-yt-iron-overlay-backdrop, #dialog').forEach(e => e.remove());
            const accept = [...document.querySelectorAll('tp-yt-paper-button, button')]
                .find(b => /alle akzeptieren|accept all|принять все/i.test(b.textContent||''));
            if (accept) accept.click();
        }""")
        page.wait_for_timeout(2000)
        exp = page.locator("#description-inline-expander #expand")
        if exp.count():
            exp.first.click()
            page.wait_for_timeout(1500)
        clicked = False
        for sel in ("button:has-text('Transkript')", "button:has-text('transcript')",
                    "button:has-text('Показать текст видео')",
                    "[aria-label*='Transkript']", "[aria-label*='transcript']",
                    "[aria-label*='текст видео']"):
            loc = page.locator(sel)
            if loc.count():
                loc.first.click()
                clicked = True
                break
        if not clicked:
            ctx.close()
            raise RuntimeError("кнопка транскрипта не найдена (у видео нет расшифровки?)")
        # wait for panel text; panel = smallest div containing its search box
        panel_text = ""
        for _ in range(10):
            page.wait_for_timeout(3000)
            panel_text = page.evaluate("""() => {
                const needle = /Im Transkript suchen|Search transcript|Поиск в расшифровке|Suchen/i;
                const divs = [...document.querySelectorAll('div')].filter(d =>
                    needle.test(d.innerText||'') && (d.innerText||'').length > 800);
                divs.sort((a,b) => (a.innerText||'').length - (b.innerText||'').length);
                return divs.length ? divs[0].innerText : '';
            }""") or ""
            if len(panel_text) > 800:
                break
        ctx.close()
        # clean panel text: drop mm:ss lines, "N Sekunden"-style duration lines
        lines = []
        for line in panel_text.splitlines():
            line = line.strip()
            if re.fullmatch(r"\d{1,2}:\d{2}(:\d{2})?", line):
                continue
            if re.fullmatch(r"\d+\s*(Sekunden|seconds|секунд[аы]?|сек\.?)", line, re.IGNORECASE):
                continue
            if line and "Transkript suchen" not in line and "Search transcript" not in line:
                lines.append(line)
        return " ".join(lines)
        ctx.close()
        # strip mm:ss timestamps, one phrase per line
        lines = []
        for line in panel_text.splitlines():
            line = line.strip()
            if re.fullmatch(r"\d{1,2}:\d{2}(:\d{2})?", line):
                continue
            if line:
                lines.append(line)
        return " ".join(lines)


def main():
    ap = argparse.ArgumentParser(description="YouTube link -> transcript")
    ap.add_argument("url")
    ap.add_argument("--lang", default="ru", help="subtitle/transcription language")
    ap.add_argument("--cookies-from-browser", default=None,
                    help="browser to export YouTube cookies from (chrome|firefox|edge) — "
                         "needed when YouTube asks to 'confirm you're not a bot'")
    ap.add_argument("--proxy", default=None, help="proxy for yt-dlp (http(s)/socks5 URL)")
    ap.add_argument("--cookies", default=None, help="path to cookies.txt (Netscape format), "
                    "export once via a 'Get cookies.txt LOCALLY' browser extension")
    ap.add_argument("--browser", action="store_true",
                    help="open a real browser window and scrape the transcript panel "
                         "(works when yt-dlp hits the bot-check; login to YouTube once in the window)")
    args = ap.parse_args()
    global EXTRA
    if args.cookies_from_browser:
        EXTRA += ["--cookies-from-browser", args.cookies_from_browser]
    if args.proxy:
        EXTRA += ["--proxy", args.proxy]
    if args.cookies:
        EXTRA += ["--cookies", args.cookies]

    OUT_DIR.mkdir(exist_ok=True)
    print("[1/3] метаданные...")
    try:
        meta = video_meta(args.url)
    except RuntimeError as e:
        if "confirm you" not in str(e) and "not a bot" not in str(e):
            raise
        print("      yt-dlp заблокирован бот-проверкой — включаю браузерный режим")
        args.browser = True
        meta = {}
    vid = meta.get("id", "video")
    title = meta.get("title", vid)
    dest = OUT_DIR / vid
    dest.mkdir(exist_ok=True)

    print("[2/3] субтитры (ручные -> автогенерированные)...")
    transcript, source = None, None
    if not args.browser:
        vtt = download_subtitles(args.url, args.lang, dest)
        if vtt:
            transcript = parse_vtt(vtt)
            source = "subtitles"
        if transcript is None:
            try:
                print("      субтитров нет — скачиваю аудио и расшифровываю локально...")
                audio = download_audio(args.url, dest)
                transcript = whisper_transcribe(audio, args.lang)
                source = "whisper (local)"
            except RuntimeError as e:
                if "bot" not in str(e):
                    raise
                print("      yt-dlp заблокирован бот-проверкой — перехожу в браузер...")
    if transcript is None:
        print("      браузерный режим: откроется окно — если YouTube попросит вход, залогинься один раз")
        transcript = browser_transcript(args.url, headless=not args.browser)
        source = "browser transcript panel"

    md = dest / "transcript.md"
    md.write_text(
        f"# {title}\n\n- URL: {args.url}\n- Расшифровка: {source}\n"
        f"- Собрано: {datetime.now().isoformat(timespec='minutes')}\n"
        f"- Длительность: {meta.get('duration_string', '?')}\n\n"
        f"> Материал для исследования идей и структуры. Не копировать текст дословно "
        f"в собственные сценарии (авторские права / политика YouTube).\n\n"
        f"## Расшифровка\n\n{transcript}\n", encoding="utf-8")

    print("[3/3] сохраняю в библиотеку...")
    save_to_library(vid, args.url, title, md)
    print(f"Готово: {md}")
    print(f"Символов расшифровки: {len(transcript)}")


if __name__ == "__main__":
    main()
