"""Shared FFmpeg helpers (subprocess, no LLM — architecture principle)."""

import json
import re
import subprocess
from pathlib import Path


def ff(args: list[str], capture: bool = False) -> bytes | None:
    proc = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {proc.stderr[-400:]}")
    return None


def ffprobe_duration(path: str | Path) -> float:
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "json", str(path)],
        capture_output=True, text=True, check=True)
    return float(json.loads(proc.stdout)["format"]["duration"])


def synth_silence(out: str | Path, duration_sec: float, rate: int = 24000):
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    ff(["-f", "lavfi", "-i", f"anullsrc=r={rate}:cl=mono",
        "-t", f"{duration_sec:.2f}", "-c:a", "libmp3lame", "-q:a", "9", str(out)])


def concat_audio(files: list[str | Path], out: str | Path):
    """Re-encode concat to uniform wav (24k mono) — immune to codec drift."""
    lst = Path(out).with_suffix(".txt")
    lst.parent.mkdir(parents=True, exist_ok=True)
    lst.write_text("".join(f"file '{Path(f).resolve().as_posix()}'\n" for f in files), encoding="utf-8")
    ff(["-f", "concat", "-safe", "0", "-i", str(lst),
        "-ar", "24000", "-ac", "1", "-c:a", "pcm_s16le", str(out)])


def concat_video(files: list[str | Path], out: str | Path):
    lst = Path(out).with_suffix(".txt")
    lst.write_text("".join(f"file '{Path(f).resolve().as_posix()}'\n" for f in files), encoding="utf-8")
    ff(["-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(out)])


AVAILABLE_SCENE_EFFECTS = [
    "zoom_in",
    "zoom_out",
    "pan_left_right",
    "pan_right_left",
    "tilt_up",
    "tilt_down",
    "diagonal_drift",
    "handheld_drift",
    "film_grain",
    "vignette_focus",
    "cinematic_contrast",
    "warm_grade",
    "cold_night",
    "faded_film",
    "sepia_archive",
    "letterbox_cine",
    "sharpen",
]

# Motion effects drive zoompan; overlay effects stack FFmpeg filters on top.
MOTION_EFFECTS = {
    "zoom_in", "zoom_out", "pan_left_right", "pan_right_left",
    "tilt_up", "tilt_down", "diagonal_drift", "handheld_drift",
}
OVERLAY_POST_FILTERS = {
    "film_grain": ",noise=alls=10:allf=t+u",
    "vignette_focus": ",vignette=PI/4",
    "cinematic_contrast": ",eq=contrast=1.12:brightness=-0.02:saturation=0.92",
    "warm_grade": ",eq=saturation=1.08:gamma_r=1.06:gamma_b=0.94",
    "cold_night": ",colorbalance=rs=-0.1:bs=0.14,eq=brightness=-0.03",
    "faded_film": ",curves=preset=lighter,eq=saturation=0.82",
    "sepia_archive": ",hue=s=0.3,eq=brightness=0.02,noise=alls=6:allf=t",
    "letterbox_cine": ",drawbox=y=0:h=ih*0.11:w=iw:color=black:t=fill,drawbox=y=ih-ih*0.11:h=ih*0.11:w=iw:color=black:t=fill",
    "sharpen": ",unsharp=5:5:0.6",
}


def _split_effects(effect) -> list[str]:
    """Accept a single effect name or a "+"-joined combo like "zoom_in+film_grain"."""
    if isinstance(effect, str):
        return [p.strip() for p in effect.split("+") if p.strip()]
    return [p for p in effect if p]


def render_scene_clip(image: str | Path, out: str | Path, duration: float,
                      effect: str = "zoom_in", fps: int = 25, size: str = "1920x1080"):
    """Render a dynamic video clip from a still image with anti-jitter 4x upscale
    and selectable cinematic motion/grade effects.

    `effect` may be a single name or a "+"-joined combo: the first motion effect
    (zoom/pan/tilt/drift) drives the zoompan, every overlay effect
    (film_grain/vignette_focus/cinematic_contrast) appends its filter, so e.g.
    "pan_left_right+film_grain+vignette_focus" stacks all three."""
    parts = _split_effects(effect)
    motion_parts = [p for p in parts if p in MOTION_EFFECTS]
    if motion_parts:
        motion = motion_parts[0]
    elif parts == ["cinematic_contrast"]:
        motion = "zoom_out"  # legacy: solo cinematic_contrast was a slow pull-back
    else:
        motion = "zoom_in"
    post_filter = "".join(OVERLAY_POST_FILTERS[p] for p in parts if p in OVERLAY_POST_FILTERS)

    frames = max(int(duration * fps), fps)
    w, h = size.split("x")
    big = f"{int(w) * 4}:{int(h) * 4}"

    if motion == "zoom_out":
        z = f"1.10-0.10*on/{frames}"
        x = "iw/2-(iw/zoom/2)"
        y = "ih/2-(ih/zoom/2)"
    elif motion == "pan_left_right":
        z = "1.10"
        x = f"(iw-iw/zoom)*on/{frames}"
        y = "ih/2-(ih/zoom/2)"
    elif motion == "pan_right_left":
        z = "1.10"
        x = f"(iw-iw/zoom)*(1-on/{frames})"
        y = "ih/2-(ih/zoom/2)"
    elif motion == "tilt_up":
        z = "1.10"
        x = "iw/2-(iw/zoom/2)"
        y = f"(ih-ih/zoom)*(1-on/{frames})"
    elif motion == "tilt_down":
        z = "1.10"
        x = "iw/2-(iw/zoom/2)"
        y = f"(ih-ih/zoom)*on/{frames}"
    elif motion == "diagonal_drift":
        z = f"1.05+0.07*on/{frames}"
        x = f"(iw-iw/zoom)*on/{frames}"
        y = f"(ih-ih/zoom)*on/{frames}"
    elif motion == "handheld_drift":
        z = "1.08"
        x = "iw/2-(iw/zoom/2)+sin(on/10)*20"
        y = "ih/2-(ih/zoom/2)+cos(on/13)*15"
    else:  # default "zoom_in"
        z = f"1+0.08*on/{frames}"
        x = "iw/2-(iw/zoom/2)"
        y = "ih/2-(ih/zoom/2)"

    vf = (f"scale={big},zoompan=z='{z}':d={frames}"
          f":x='{x}':y='{y}':s={size}:fps={fps}{post_filter}")
    ff(["-loop", "1", "-i", str(image), "-vf", vf, "-t", f"{duration:.2f}",
        "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p", str(out)])


def ken_burns(image: str | Path, out: str | Path, duration: float, zoom_in: bool = True,
              fps: int = 25, size: str = "1920x1080"):
    """Legacy wrapper for ken_burns: calls render_scene_clip with zoom_in / zoom_out."""
    render_scene_clip(image, out, duration, effect="zoom_in" if zoom_in else "zoom_out", fps=fps, size=size)


def xfade_chain(files: list[str | Path], durations: list[float], out: str | Path,
                fade: float = 1.2, fade_in: float = 2.0, fade_out: float = 3.0,
                size: str = "1920x1080"):
    """Join scene clips with crossfades in a single filter_complex pass, plus
    fade-from-black at the start and fade-to-black at the end ("затухания" per
    the video guide). Output duration = sum(durations) - fade*(n-1)."""
    n = len(files)
    if n == 1:
        ff(["-i", str(files[0]),
            "-vf", f"scale={size},fade=t=in:st=0:d={fade_in},fade=t=out:st={max(durations[0] - fade_out, 0):.3f}:d={fade_out}",
            "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p", str(out)])
        return
    inputs: list[str] = []
    for f in files:
        inputs += ["-i", str(f)]
    parts, prev, prev_dur = [], "[0:v]", durations[0]
    for k in range(1, n):
        outlbl = f"[v{k}]" if k < n - 1 else "[vxf]"
        offset = prev_dur - fade
        parts.append(f"{prev}[{k}:v]xfade=transition=fade:duration={fade}:offset={offset:.3f}{outlbl}")
        prev = outlbl
        prev_dur = prev_dur + durations[k] - fade
    total = prev_dur
    last = "[vxf]"
    if fade_in > 0:
        parts.append(f"[vxf]fade=t=in:st=0:d={fade_in}[vin]")
        last = "[vin]"
    if fade_out > 0:
        parts.append(f"{last}fade=t=out:st={max(total - fade_out, 0):.3f}:d={fade_out}[vout]")
        last = "[vout]"
    parts.append(f"{last}scale={size}[vscaled]")
    ff([*inputs, "-filter_complex", ";".join(parts), "-map", "[vscaled]",
        "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p", str(out)])


def mix_and_master(voice: str | Path, ambient: str | Path | None,
                   out: str | Path, ambient_db: float = -27.0):
    """Voice loudnorm to -14 LUFS + ambient bed under it, AAC out."""
    if ambient and Path(ambient).exists():
        fc = ("[0:a]loudnorm=I=-14:TP=-1.5:LRA=11[voice];"
              f"[1:a]volume={ambient_db}dB[bed];"
              "[voice][bed]amix=inputs=2:duration=first:dropout_transition=0[aout]")
        ff(["-i", str(voice), "-i", str(ambient), "-filter_complex", fc,
            "-map", "[aout]", "-c:a", "aac", "-b:a", "160k", str(out)])
    else:
        fc = "[0:a]loudnorm=I=-14:TP=-1.5:LRA=11[aout]"
        ff(["-i", str(voice), "-filter_complex", fc,
            "-map", "[aout]", "-c:a", "aac", "-b:a", "160k", str(out)])


def mux(video: str | Path, audio: str | Path, out: str | Path):
    ff(["-i", str(video), "-i", str(audio), "-map", "0:v", "-map", "1:a",
        "-c:v", "copy", "-c:a", "copy", "-shortest", str(out)])


def drawtext_card(out: str | Path, text: str, bg: str = "0x1E1A4E", accent: str = "0xE1C049",
                  size: str = "1920x1080", font: str | None = None):
    """Thumbnail/cover placeholder: flat background + text (real image gen in S5 later)."""
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    font = (font or r"C:/Windows/Fonts/arialbd.ttf").replace(":", r"\:")
    safe = re.sub(r"[^\w\s.,!?:-]", "", text)[:40] or "EPISODE"
    safe = safe.replace(":", r"\:")
    ff(["-f", "lavfi", "-i", f"color=c={bg}:s={size}:d=1",
        "-vf", (f"drawtext=fontfile='{font}':text='{safe}':fontcolor={accent}:fontsize=140:"
                f"x=(w-text_w)/2:y=(h-text_h)/2"),
        "-frames:v", "1", str(out)])


def srt_time(sec: float) -> str:
    ms = int(round(sec * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def write_srt(lines: list[dict], out: str | Path):
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    blocks = []
    for i, ln in enumerate(lines, start=1):
        blocks.append(f"{i}\n{srt_time(ln['start'])} --> {srt_time(ln['end'])}\n{ln['text']}\n")
    out.write_text("\n".join(blocks), encoding="utf-8")
