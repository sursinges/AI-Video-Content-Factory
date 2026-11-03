"""M5 metadata module (S5): LLM publish kit + cover. The cover is a real
provider-generated image when an image provider works, with a drawtext-card
fallback when it does not (S5-02)."""

import json

from core.contracts import Chapter, Metadata, ThumbnailSpec
from core.media import drawtext_card, overlay_title_text
from modules.base import Artifact, Module, RunContext
from modules.m1_script.prompts import extract_json, render


class M5Metadata(Module):
    name = "m5_metadata"

    def run(self, ctx: RunContext) -> list[Artifact]:
        script = json.loads((ctx.run_dir / "script" / "script.json").read_text(encoding="utf-8"))
        audio = json.loads((ctx.run_dir / "audio" / "audio_result.json").read_text(encoding="utf-8"))
        summary = " ".join(c["text"][:500] for c in script["chunks"])[:3500]
        minutes = round(audio["duration_sec"] / 60)

        if ctx.dry_run:
            title = ctx.manifest.topic[:70]
            tags = ["mock", "sleep", "history"]
            thumb_text = "ИСТОРИЯ НОЧИ"[:20]
            description = f"MOCK DESCRIPTION — {ctx.manifest.topic}. Спокойная история под засыпание."
        else:
            try:
                resp = ctx.router.call("llm", {"prompt": render("metadata_series.md", {
                    "topic": ctx.manifest.topic, "language": ctx.manifest.language,
                    "minutes": minutes, "summary": summary}), "temperature": 0.6})
                data = extract_json(resp.get("text", "")) or {}
                title = str(data.get("title") or ctx.manifest.topic)[:70]
                description = str(data.get("description") or ctx.manifest.topic)
                tags = [str(t) for t in data.get("tags", [])][:15]
                thumb_text = str(data.get("thumbnail_text") or title[:20])
            except Exception as e:
                ctx.router.on_event(f"m5_metadata LLM notice: {e}, using fallback metadata")
                title = f"{ctx.manifest.topic} — Забытая война, изменившая всё"[:70]
                description = (
                    f"{ctx.manifest.topic}. Атмосферная историческая история под засыпание.\n\n"
                    f"{summary[:400]}...\n\n"
                    "Спокойного прослушивания и добрых снов."
                )
                tags = ["история", "гражданская война", "испания", "под засыпание", "ночная история", "аудиокнига", "сон"]
                thumb_text = "ИСПАНИЯ 1936"

        # chapters: one per script part, timed from audio part durations
        chapters, t = [], 0.0
        for i, dur in enumerate(audio.get("parts", []), start=1):
            m, s = divmod(int(t), 60)
            chapters.append(Chapter(t=f"{m:02d}:{s:02d}", label=f"Часть {i}"))
            t += dur

        thumb_path = ctx.run_dir / "metadata" / "thumbnail.png"

        # Cover: real provider image + title overlay; drawtext-card fallback.
        vis_cfg = ctx.profile.get("visual", {})
        preset_name = vis_cfg.get("preset") or (getattr(ctx.manifest, "custom", None) or {}).get("visual_preset")
        cover_prompt = None
        try:
            from core.branding import brand_cover_suffix
            from modules.m3_visual.runner import _load_visual_preset

            preset = _load_visual_preset(preset_name)
            parts = [preset.get("style_prompt"), preset.get("quality_tags")]
            cover_prompt = ", ".join(p for p in parts if p)
            brand = brand_cover_suffix((ctx.data_root or ctx.workspace) / "config")
            if brand:
                cover_prompt = f"{cover_prompt}, {brand}"
            ctx.router.call("image", {"prompt": cover_prompt,
                                      "negative": preset.get("negative_prompt"),
                                      "out_path": str(thumb_path), "width": 1280, "height": 720})
            overlay_title_text(thumb_path, thumb_text)
        except Exception as e:  # noqa: BLE001 — cover art is optional, fallback is guaranteed
            ctx.router.on_event(f"m5_metadata cover notice: {e}, using drawtext fallback")
            cover_prompt = None
            drawtext_card(thumb_path, thumb_text)

        meta = Metadata(
            title=title, description=description, tags=tags, chapters=chapters,
            thumbnail=ThumbnailSpec(text_overlay=thumb_text, asset=str(thumb_path),
                                    ref=cover_prompt),
        )
        return [("metadata/metadata.json", meta)]
