"""M4 assembly module (S4): real FFmpeg — Ken Burns per scene (anti-jitter
upscale), crossfade joins + fade in/out ("затухания" per the video guide,
owner feedback on ep-0003/4), voice loudnorm -14 LUFS + ambient bed, mux.
No LLM here by design."""

import json
from pathlib import Path

from core.contracts import AssemblyResult
from core.media import (
    AVAILABLE_SCENE_EFFECTS,
    ff,
    ffprobe_duration,
    mix_and_master,
    mux,
    render_scene_clip,
    xfade_chain,
)
from modules.base import Artifact, Module, RunContext

FADE = 1.2  # crossfade between scenes, sec


class M4Assembly(Module):
    name = "m4_assembly"

    def run(self, ctx: RunContext) -> list[Artifact]:
        scenes = json.loads((ctx.run_dir / "visual" / "scenes.json").read_text(encoding="utf-8"))["scenes"]
        audio_res = json.loads((ctx.run_dir / "audio" / "audio_result.json").read_text(encoding="utf-8"))
        mix_cfg = ctx.profile.get("audio_mix", {})

        voice = audio_res["episode_path"]
        if not voice or not Path(voice).exists():
            raise RuntimeError("m4: episode audio missing — run m2 first")
        total_dur = audio_res["duration_sec"]

        work = ctx.run_dir / "video" / "_work"
        work.mkdir(parents=True, exist_ok=True)
        size = "x".join(str(v) for v in ctx.profile.get("visual", {}).get("resolution", [1920, 1080]))

        # 1) Cinematic motion per scene with modular FFmpeg effects.
        # Crossfades eat fade*(n-1) seconds of the timeline, so raw scene
        # lengths are scaled up to keep the final video exactly as long as the audio.
        base = [max(sc["end"] - sc["start"], 0.4) for sc in scenes]
        k = max(len(scenes) - 1, 0)
        scale = (total_dur + FADE * k) / sum(base)
        durations = [b * scale for b in base]

        scene_files = []
        applied_effects = []
        for i, sc in enumerate(scenes):
            out = work / f"scene_{i:03d}.mp4"
            effect = sc.get("effect") or AVAILABLE_SCENE_EFFECTS[i % len(AVAILABLE_SCENE_EFFECTS)]
            render_scene_clip(sc["asset"], out, duration=durations[i], effect=effect, size=size)
            applied_effects.append({
                "index": i + 1,
                "scene_id": sc.get("id", f"s{i+1:03d}"),
                "start": sc.get("start", 0.0),
                "end": sc.get("end", 0.0),
                "effect": effect,
                "duration": round(durations[i], 2),
            })
            scene_files.append(out)

        (ctx.run_dir / "video" / "effects_report.json").write_text(
            json.dumps(applied_effects, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        # 2) Crossfade join + fade from/to black
        silent = work / "video_silent.mp4"
        xfade_chain(scene_files, durations, silent, fade=FADE, size=size)

        # 3) Ambient bed via music provider (procedural synth / library / jamendo)
        ambient = work / "ambient.m4a"
        music_mood = (ctx.profile.get("music_mood")
                      or (ctx.profile.get("music") or {}).get("mood") or "night")
        ctx.router.call("music", {"out_path": str(ambient), "duration_sec": total_dur,
                                    "mood": music_mood})

        # 4) Voice loudnorm + ambient mix, then mux (-shortest guards ~0.1s drift)
        mixed = work / "audio_mixed.m4a"
        lo, hi = mix_cfg.get("ambient_db", [-25, -30])
        mix_and_master(voice, ambient, mixed, ambient_db=(lo + hi) / 2)
        final = ctx.run_dir / "video" / "episode.mp4"
        mux(silent, mixed, final)

        duration = ffprobe_duration(final)
        if abs(duration - total_dur) > 1.0:
            raise RuntimeError(
                f"m4: video duration {duration:.1f}s deviates from audio {total_dur:.1f}s")

        # 4b) Optional burned-in subtitles (profile/override subtitles.burn_in)
        sub_cfg = (ctx.profile.get("subtitles") or {})
        if sub_cfg.get("burn_in"):
            srt = ctx.run_dir / "subtitles" / "subtitles.srt"
            if srt.exists():
                presets = {
                    "minimal": "FontName=Arial,Fontsize=44,PrimaryColour=&H00FFFFFF,Outline=2,Shadow=0,MarginV=46",
                    "bold_yellow": "FontName=Arial Bold,Fontsize=48,PrimaryColour=&H0054D7FF,OutlineColour=&H00000000,Outline=4,Bold=1,MarginV=50",
                    "boxed": "FontName=Arial,Fontsize=44,PrimaryColour=&H00FFFFFF,BackColour=&H80000000,BorderStyle=4,MarginV=46",
                }
                style = presets.get(sub_cfg.get("style", "minimal"), presets["minimal"])
                if sub_cfg.get("font_size"):
                    style += f",Fontsize={int(sub_cfg['font_size'])}"
                srt_esc = srt.resolve().as_posix().replace(':', '\:')
                burned = work / "episode_burned.mp4"
                ff(["-i", str(final), "-vf",
                    f"subtitles='{srt_esc}':force_style='{style}'",
                    "-c:v", "libx264", "-preset", "fast", "-crf", "20",
                    "-c:a", "copy", str(burned)])
                burned.replace(final)

        # 5) Generate accurate timecodes (Feature 1 & 2)
        t_cur = 0.0
        tc_lines = []
        tc_items = []
        for i, sc in enumerate(scenes):
            dur = durations[i]
            mm = int(t_cur // 60)
            ss = int(t_cur % 60)
            hh = int(mm // 60)
            tc_str = f"{hh:02d}:{mm%60:02d}:{ss:02d}" if hh > 0 else f"{mm:02d}:{ss:02d}"
            text_str = (sc.get("text") or sc.get("text_ref") or "").replace("|", " ").strip()
            # Clean headline for YouTube description
            words = text_str.split()
            short_title = " ".join(words[:7]) if words else f"Scene {i+1}"
            if len(short_title) > 50:
                short_title = short_title[:47] + "..."
            tc_lines.append(f"{tc_str} {short_title}")
            tc_items.append({
                "index": i + 1,
                "scene_id": sc.get("id", f"s{i+1:03d}"),
                "timecode": tc_str,
                "start_sec": round(t_cur, 2),
                "end_sec": round(t_cur + dur, 2),
                "duration_sec": round(dur, 2),
                "effect": applied_effects[i]["effect"] if i < len(applied_effects) else "zoom_in",
                "text": text_str,
                "asset": sc.get("asset", "")
            })
            t_cur += (dur - FADE) if i < len(scenes) - 1 else dur

        (ctx.run_dir / "video" / "timecodes.txt").write_text("\n".join(tc_lines), encoding="utf-8")
        (ctx.run_dir / "video" / "timecodes.json").write_text(
            json.dumps(tc_items, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        # 6) Custom folder export (Feature 8)
        export_target = getattr(ctx.manifest, "export_dir", None) or (ctx.manifest.overrides or {}).get("export_dir")
        exported_files = []
        if export_target:
            import shutil
            exp_p = Path(export_target)
            exp_p.mkdir(parents=True, exist_ok=True)
            run_prefix = ctx.manifest.run_id
            target_vid = exp_p / f"{run_prefix}.mp4"
            shutil.copy2(final, target_vid)
            exported_files.append(str(target_vid))
            target_tc = exp_p / f"{run_prefix}_timecodes.txt"
            shutil.copy2(ctx.run_dir / "video" / "timecodes.txt", target_tc)
            exported_files.append(str(target_tc))
            target_tc_json = exp_p / f"{run_prefix}_timecodes.json"
            shutil.copy2(ctx.run_dir / "video" / "timecodes.json", target_tc_json)
            exported_files.append(str(target_tc_json))
            thumb = ctx.run_dir / "metadata" / "thumbnail.png"
            if thumb.exists():
                target_thumb = exp_p / f"{run_prefix}_thumbnail.png"
                shutil.copy2(thumb, target_thumb)
                exported_files.append(str(target_thumb))
            srt = ctx.run_dir / "subtitles" / "subtitles.srt"
            if srt.exists():
                target_srt = exp_p / f"{run_prefix}.srt"
                shutil.copy2(srt, target_srt)
                exported_files.append(str(target_srt))

        return [("video/assembly_result.json",
                 AssemblyResult(video_path=str(final), duration_sec=round(duration, 2),
                                voice_lufs=-14.0,
                                notes=f"ken_burns(4x upscale)+xfade({FADE}s)+fades" +
                                      (f" | exported_to={export_target}" if export_target else "")))]

