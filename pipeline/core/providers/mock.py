"""Deterministic mock providers: pipeline runs fully without keys/network.
TTS/image/music mocks synthesize REAL artifact files via ffmpeg (silence /
solid color), so the conveyor can assemble a true video without paid APIs."""

import hashlib
import json
import subprocess
from pathlib import Path

from core.providers.router import Provider


def _ffmpeg(args: list[str]):
    proc = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg exit {proc.returncode}: {proc.stderr[-400:]}")


class MockProvider(Provider):
    adapter = "mock"

    def execute(self, payload: dict) -> dict:
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:8]
        if self.ptype == "llm":
            return {"text": f"[MOCK:{self.name}:{digest}] {payload.get('prompt', '')[:64]}"}
        if self.ptype in ("tts", "image", "music"):
            out = payload.get("out_path")
            if not out:
                raise ValueError(f"{self.ptype} mock requires out_path")
            Path(out).parent.mkdir(parents=True, exist_ok=True)
        else:
            out = None
        if self.ptype == "tts":
            out = payload.get("out_path")
            if not out:
                raise ValueError("tts mock requires out_path")
            # cap: mock speech is meaningless beyond a few seconds and keeps
            # dry-run video rendering fast
            dur = min(5.0, max(0.8, len(payload.get("text", "")) / 14.0))  # ~14 chars/sec speech
            _ffmpeg(["-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
                     "-t", f"{dur:.2f}", "-q:a", "9", out])
            return {"audio_path": out, "duration_sec": round(dur, 2)}
        if self.ptype == "image":
            out = payload.get("out_path")
            if not out:
                raise ValueError("image mock requires out_path")
            _ffmpeg(["-f", "lavfi", "-i",
                     f"color=c=0x1E1A4E:s=1920x1080:d=1",
                     "-frames:v", "1", out])
            return {"image_path": out}
        if self.ptype == "music":
            out = payload.get("out_path")
            dur = payload.get("duration_sec", 10)
            _ffmpeg(["-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
                     "-t", f"{float(dur):.2f}", out])
            return {"audio_path": out, "duration_sec": dur}
        if self.ptype == "video":
            # GAP-01 scaffold: real mp4 clip so the image->video path is
            # testable without keys — slow zoom on the image, or a color source.
            out = payload.get("out_path")
            if not out:
                raise ValueError("video mock requires out_path")
            Path(out).parent.mkdir(parents=True, exist_ok=True)
            dur = float(payload.get("duration_sec", 4))
            img = payload.get("image_path") or ""
            if img and Path(img).exists():
                _ffmpeg(["-loop", "1", "-i", str(img), "-t", f"{dur:.2f}",
                         "-vf", "scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720,"
                                "zoompan=z='min(zoom+0.0008,1.12)':d=1:s=1280x720:fps=25",
                         "-c:v", "libx264", "-pix_fmt", "yuv420p", out])
            else:
                _ffmpeg(["-f", "lavfi", "-i", f"color=c=0x1E1A4E:s=1280x720:d={dur:.2f}:r=25",
                         "-c:v", "libx264", "-pix_fmt", "yuv420p", out])
            return {"video_path": out, "duration_sec": dur}
        if self.ptype == "stt":
            return {"words": [{"w": "mock", "start": 0.0, "end": 0.4}], "language": payload.get("language", "ru")}
        if self.ptype == "publish":
            return {"video_id": f"mock_{digest}", "status": "mock"}
        raise NotImplementedError(f"mock for ptype '{self.ptype}'")
