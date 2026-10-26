"""M3 visual module (S3): world context -> critic -> scene plan -> images.
Scene boundaries are computed deterministically from subtitle timings; the
LLM only writes per-scene prompts (times from an LLM are not trusted)."""

import json
import zlib

from core.contracts import Scene, Scenes, WorldContext
from modules.base import Artifact, Module, RunContext
from modules.m1_script.prompts import extract_json, render


def _summary_from_script(ctx) -> str:
    script = json.loads((ctx.run_dir / "script" / "script.json").read_text(encoding="utf-8"))
    return " ".join(c["text"][:600] for c in script["chunks"])[:4000]


def _snap_to_pause(words: list[dict], t: float, window: float = 4.0) -> float:
    """Move a scene boundary to the nearest speech pause (>=0.3 s gap between
    words) within +-window seconds, so cuts never land mid-word (owner feedback:
    clips used to change between words). Returns t if no pause found."""
    best, best_gap = t, 0.0
    for a, b in zip(words, words[1:]):
        gap = b["start"] - a["end"]
        if gap < 0.3:
            continue
        mid = (a["end"] + b["start"]) / 2
        if abs(mid - t) < window and gap > best_gap:
            best, best_gap = mid, gap
    return best


def _build_scenes(ctx, subs: dict, world: WorldContext, prompts: list[str] | None) -> list[Scene]:
    """Deterministic boundaries: one scene per ~45 s of speech, snapped to
    pauses; whisper timestamps are clamped monotonic."""
    vis = ctx.profile.get("visual", {})
    lo, hi = vis.get("scene_change_seconds", [30, 60])
    target = (lo + hi) / 2
    lines = subs["lines"]
    words = subs.get("words", [])
    scenes, block, block_start = [], [], None

    def flush():
        nonlocal block, block_start
        if not block:
            return
        prompt = "flat vector night scene, calm sleep mood, dark palette, no text"
        if prompts and len(scenes) < len(prompts):
            prompt = prompts[len(scenes)]
        scenes.append(Scene(
            id=f"s{len(scenes) + 1:03d}", start=round(block_start, 2),
            end=round(block[-1]["end"], 2),
            text_ref=" | ".join(b["text"][:40] for b in block)[:120],
            prompt=prompt, negative=", ".join(world.forbidden) + ", text, letters, watermark",
            seed=(zlib.crc32(world.era.encode("utf-8")) + len(scenes) * 7919) % 100000,
            status="pending"))
        block, block_start = [], None

    last_end = lines[-1]["end"] if lines else 0.0
    targets, pos = [], 0.0
    for ln in lines:
        pos = ln["end"]
        if pos - (targets[-1] if targets else 0.0) >= target:
            targets.append(_snap_to_pause(words, pos))
    bounds = sorted({t for t in targets if 0 < t < last_end - 5.0} | {last_end})

    prev = 0.0
    for b in bounds:
        b = max(b, prev + 1.0)
        for ln in lines:
            if prev <= ln["start"] < b:
                if block_start is None:
                    block_start = max(ln["start"], prev)
                block.append(ln)
        flush()
        prev = b
    if not scenes:
        for ln in lines:
            if block_start is None:
                block_start = ln["start"]
            block.append(ln)
        flush()
    return scenes


def _load_visual_preset(preset_key: str | None = None) -> dict:
    from pathlib import Path
    import yaml
    cfg_file = Path(__file__).resolve().parent.parent.parent / "config" / "visual_presets.yaml"
    custom_file = Path(__file__).resolve().parent.parent.parent / "config" / "visual_presets_custom.yaml"
    if cfg_file.exists():
        try:
            data = yaml.safe_load(cfg_file.read_text(encoding="utf-8")) or {}
            presets = dict(data.get("presets") or {})
            if custom_file.exists():
                custom = yaml.safe_load(custom_file.read_text(encoding="utf-8")) or {}
                presets.update(custom.get("presets") or {})
            key = preset_key or data.get("default_preset", "dark_history_cinematic")
            if key in presets:
                return presets[key]
        except Exception:
            pass
    if custom_file.exists():
        try:
            custom = yaml.safe_load(custom_file.read_text(encoding="utf-8")) or {}
            presets_c = custom.get("presets") or {}
            if preset_key and preset_key in presets_c:
                return presets_c[preset_key]
        except Exception:
            pass
    return {
        "name": "Dark History (Cinematic 35mm)",
        "style_prompt": "dark historical documentary, authentic archival atmosphere, moody volumetric cinematic lighting, deep dramatic shadows, chiaroscuro, 35mm film photograph, gritty realistic textures, desaturated historical palette, photorealistic, 8k, cinematic composition, masterwork",
        "negative_prompt": "cartoon, 3d render, anime, cgi, vibrant bright colors, neon, oversaturated, smooth plastic, digital illustration, drawing, painting, collage, split screen, multiple frames, distorted faces, modern objects, watermark, text, signature, bad anatomy",
    }


class M3Visual(Module):
    name = "m3_visual"

    def run(self, ctx: RunContext) -> list[Artifact]:
        subs = json.loads((ctx.run_dir / "subtitles" / "subtitles.json").read_text(encoding="utf-8"))
        summary = _summary_from_script(ctx)
        vis_cfg = ctx.profile.get("visual", {})
        preset_name = vis_cfg.get("preset") or (getattr(ctx.manifest, "custom", None) or {}).get("visual_preset")
        preset = _load_visual_preset(preset_name)
        style = preset.get("style_prompt") or vis_cfg.get("style_preset", "dark historical documentary, authentic archival atmosphere")
        neg_preset = preset.get("negative_prompt", "cartoon, 3d render, anime, vibrant colors, neon, text, watermark")

        # 1) world context (LLM; deterministic mock in dry-run)
        if ctx.dry_run:
            world = WorldContext(era="MOCK ERA", palette=["#1E1A4E", "#E1C049", "#0C0A26"],
                                 light="moonlight, warm lantern", forbidden=["modern objects", "neon"])
        else:
            try:
                resp = ctx.router.call("llm", {"prompt": render("world_context.md", {
                    "topic": ctx.manifest.topic, "summary": summary}), "temperature": 0.4})
                world = WorldContext(**(extract_json(resp.get("text", "")) or {}))
            except Exception as e:
                ctx.router.on_event(f"m3_visual world_context notice: {e}, using default world")
                world = WorldContext(
                    era="1930s Spain",
                    palette=["#1E1A4E", "#E1C049", "#0C0A26", "#8B0000"],
                    light="moonlight, warm lantern, dramatic night shadows",
                    forbidden=["modern objects", "neon", "cars", "smartphones"],
                )

            # 2) critic pass over the world context
            try:
                resp = ctx.router.call("llm", {"prompt": render("critic_visual.md", {
                    "topic": ctx.manifest.topic, "summary": summary,
                    "world": world.model_dump_json()}), "temperature": 0.2})
                fixed = extract_json(resp.get("text", ""))
                if fixed:
                    world = WorldContext(**fixed)
            except Exception:  # noqa: BLE001 — keep pre-critic world on bad JSON or network
                pass

        # 3) scene plan with deterministic timings
        scenes = _build_scenes(ctx, subs, world, prompts=None)
        full_negative = f"{neg_preset}, {', '.join(world.forbidden)}, text, watermark, signature"

        # 4) per-block prompts (one LLM call per ~5 minutes of scenes)
        prompts: list[str] = []
        if not ctx.dry_run:
            block, block_ids = [], []
            for sc in scenes:
                sc.negative = full_negative
                block.append(sc.text_ref)
                block_ids.append(sc.id)
                if len(block) >= 7 or sc is scenes[-1]:
                    got = []
                    try:
                        resp = ctx.router.call("llm", {"prompt": render("scene_prompts.md", {
                            "style_preset": style,
                            "palette": ", ".join(world.palette),
                            "light": world.light,
                            "forbidden": ", ".join(world.forbidden),
                            "language": ctx.manifest.language,
                            "scenes_text": "\n".join(f"{sid}: {t}" for sid, t in zip(block_ids, block)),
                        }), "temperature": 0.7})
                        data = extract_json(resp.get("text", "")) or {}
                        got = [p for p in data.get("prompts", []) if isinstance(p, str)]
                    except Exception as e:
                        ctx.router.on_event(f"m3_visual scene_prompts notice: {e}, using fallback prompts")
                    # LLM may return fewer prompts than scenes or fail — pad deterministically
                    for i, sc_item in enumerate(scenes[len(prompts):len(prompts) + len(block)]):
                        prompts.append(got[i] if i < len(got) else
                                       f"{style}, {world.era}, {world.light}, {sc_item.text_ref}, calm sleep mood, no text")
                    block, block_ids = [], []

        # 5) image generation per scene — SKIPPED in draft plan (storyboard
        #    shows grey placeholders with real prompts; the render re-runs m3)
        if (ctx.profile.get("visual") or {}).get("plan_only"):
            for sc in scenes:
                sc.status = "planned"
            ctx.router.on_event("m3_visual DRAFT: scene plan only, image generation skipped")
            return [("visual/world.json", world), ("visual/scenes.json", Scenes(scenes=scenes))]

        img_dir = ctx.run_dir / "visual" / "assets"
        for i, sc in enumerate(scenes):
            sc.negative = full_negative
            if prompts:
                sc.prompt = prompts[i]
            out = img_dir / f"{sc.id}.png"
            res = ctx.router.call("image", {"prompt": sc.prompt, "negative": sc.negative,
                                            "seed": sc.seed, "out_path": str(out),
                                            "width": vis_cfg.get("image_size", [1024, 576])[0],
                                            "height": vis_cfg.get("image_size", [1024, 576])[1]})
            sc.asset = res.get("image_path", str(out))
            sc.status = "done"

        return [("visual/world.json", world), ("visual/scenes.json", Scenes(scenes=scenes))]
