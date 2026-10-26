"""Adaptation engine: transforms third-party transcripts / scripts into original channel scripts.

Principles:
1. Fresh perspective (новый взгляд) and charisma preservation.
2. Narrative rearrangement (перестановка данных, нелинейная подача, кульминация/парадокс в начале).
3. Mood transformation (смена настроения, кинематографичный саспенс / засыпание).
4. Strict length preservation (никакого укорачивания в 10-100 раз; поблочная генерация для длинных текстов).
5. Clean voiceover text (TTS-ready, no timestamps or stage directions).
"""

import math
import re
from pathlib import Path
from string import Template

from core.contracts import Script
from core.providers.router import Router
from core.script_cleaner import clean_script_text


def split_text_into_scenes(text: str, n_scenes: int) -> list[str]:
    """Splits text into n_scenes approximately equal parts at paragraph or sentence boundaries."""
    if n_scenes <= 1 or len(text) < 2000:
        return [text]

    chunks: list[str] = []
    remaining = text.strip()

    for _ in range(n_scenes - 1):
        scenes_left = n_scenes - len(chunks)
        if scenes_left <= 1:
            break
        target_chunk_len = len(remaining) / scenes_left
        search_pos = int(target_chunk_len)
        # Search for paragraph boundary near target_chunk_len (+/- 800 chars)
        window_start = max(100, search_pos - 800)
        window_end = min(len(remaining) - 100, search_pos + 800)
        window = remaining[window_start:window_end]

        # Find paragraph boundary closest to search_pos
        target_offset = search_pos - window_start
        para_matches = [m.end() for m in re.finditer(r'\n\s*\n', window)]
        if para_matches:
            best_offset = min(para_matches, key=lambda pos: abs(pos - target_offset))
            split_idx = window_start + best_offset
        else:
            # Look for sentence end followed by space
            sent_matches = [m.end() for m in re.finditer(r'[.!?]\s+', window)]
            if sent_matches:
                best_offset = min(sent_matches, key=lambda pos: abs(pos - target_offset))
                split_idx = window_start + best_offset
            else:
                # Fallback: space
                sp_idx = window.rfind(" ")
                if sp_idx != -1:
                    split_idx = window_start + sp_idx + 1
                else:
                    split_idx = search_pos

        chunk = remaining[:split_idx].strip()
        chunks.append(chunk)
        remaining = remaining[split_idx:].strip()

    if remaining:
        chunks.append(remaining)

    return chunks


def run_script_adaptation(
    source_text: str,
    profile: dict,
    router: Router,
    workspace: Path,
    target_minutes: int | None = None,
    script_notes: str = "",
    language: str = "ru",
) -> dict:
    """Adapts source_text into a full-scale channel script preserving volume, essence, and charisma."""
    cleaned_source = clean_script_text(source_text) or source_text.strip()
    source_chars = len(cleaned_source)
    if not source_chars:
        return {"error": "текст сценария пуст"}

    # Estimate natural minutes if not explicitly given or if given as 1 for long text
    source_est_minutes = max(1, round(source_chars / 900))
    if not target_minutes or (target_minutes <= 1 and source_est_minutes > 1):
        target_minutes = source_est_minutes

    channel_name = profile.get("name", "Наш канал")
    tone = profile.get("tone", "спокойный, атмосферный, умиротворяющий")
    final_phrase = profile.get("final_phrase", "Спокойной ночи.")
    notes_block = f"\n## Особые пометки и пожелания автора (длительность, акценты, стиль):\n{script_notes}\n" if script_notes else ""

    # Choose strategy: Single-pass (<= 5,500 chars) or Multi-scene pass (> 5,500 chars)
    if source_chars <= 5500:
        return _adapt_single_pass(
            cleaned_source=cleaned_source,
            source_chars=source_chars,
            target_minutes=target_minutes,
            channel_name=channel_name,
            tone=tone,
            language=language,
            final_phrase=final_phrase,
            notes_block=notes_block,
            router=router,
            workspace=workspace,
        )
    else:
        return _adapt_multi_scene_pass(
            cleaned_source=cleaned_source,
            source_chars=source_chars,
            target_minutes=target_minutes,
            channel_name=channel_name,
            tone=tone,
            language=language,
            final_phrase=final_phrase,
            notes_block=notes_block,
            router=router,
            workspace=workspace,
        )


def _adapt_single_pass(
    cleaned_source: str,
    source_chars: int,
    target_minutes: int,
    channel_name: str,
    tone: str,
    language: str,
    final_phrase: str,
    notes_block: str,
    router: Router,
    workspace: Path,
) -> dict:
    prompt_path = workspace / "prompts" / "adapt_script.md"
    if not prompt_path.exists():
        return {"error": "шаблон prompts/adapt_script.md не найден"}

    min_target_chars = max(1500, int(source_chars * 0.85))
    prompt_raw = prompt_path.read_text(encoding="utf-8")
    prompt_lines = [l for l in prompt_raw.splitlines() if not l.startswith("#")]
    tpl = Template("\n".join(prompt_lines))

    prompt = tpl.safe_substitute(
        channel_name=channel_name,
        tone=tone,
        language=language,
        target_minutes=target_minutes,
        source_chars=source_chars,
        min_target_chars=min_target_chars,
        final_phrase=final_phrase,
        source_text=cleaned_source,
        script_notes=notes_block,
    )

    resp = router.call("llm", {
        "prompt": prompt,
        "temperature": 0.7,
        "max_tokens": 4096,
    })
    raw_adapted = resp.get("text", "")
    adapted = clean_script_text(raw_adapted)

    if final_phrase and final_phrase.strip().lower() not in adapted.lower():
        adapted = f"{adapted.rstrip()}\n\n{final_phrase}"

    return {
        "ok": True,
        "script": adapted,
        "char_count": len(adapted),
        "source_chars": source_chars,
        "scenes_count": 1,
    }


def _adapt_multi_scene_pass(
    cleaned_source: str,
    source_chars: int,
    target_minutes: int,
    channel_name: str,
    tone: str,
    language: str,
    final_phrase: str,
    notes_block: str,
    router: Router,
    workspace: Path,
) -> dict:
    bp_path = workspace / "prompts" / "adapt_blueprint.md"
    scene_path = workspace / "prompts" / "adapt_scene.md"
    if not bp_path.exists() or not scene_path.exists():
        return {"error": "шаблоны prompts/adapt_blueprint.md или adapt_scene.md не найдены"}

    # Determine number of scenes (each ~4,000 - 5,500 chars of source)
    n_scenes = min(6, max(2, round(source_chars / 4500)))
    scenes_source = split_text_into_scenes(cleaned_source, n_scenes)
    actual_scenes = len(scenes_source)

    # 1. Blueprint pass: create architecture of rearrangement and fresh angle
    bp_raw = bp_path.read_text(encoding="utf-8")
    bp_lines = [l for l in bp_raw.splitlines() if not l.startswith("#")]
    bp_tpl = Template("\n".join(bp_lines))

    # Send up to 25,000 chars of source overview for blueprint planning
    source_overview = cleaned_source[:25000]
    bp_prompt = bp_tpl.safe_substitute(
        channel_name=channel_name,
        tone=tone,
        language=language,
        target_minutes=target_minutes,
        parts_count=actual_scenes,
        script_notes=notes_block,
        source_text=source_overview,
    )

    bp_resp = router.call("llm", {
        "prompt": bp_prompt,
        "temperature": 0.7,
        "max_tokens": 2048,
    })
    blueprint = bp_resp.get("text", "")

    # 2. Scene-by-scene generation: full prose, zero compression
    scene_raw = scene_path.read_text(encoding="utf-8")
    scene_lines = [l for l in scene_raw.splitlines() if not l.startswith("#")]
    scene_tpl = Template("\n".join(scene_lines))

    generated_scenes: list[str] = []
    prev_tail = ""

    for idx, sc_src in enumerate(scenes_source, start=1):
        is_final = (idx == actual_scenes)
        min_chars = max(1800, int(len(sc_src) * 0.85))

        prev_ctx = f"## Окончание предыдущей части (сохраняй плавную связку):\n«...{prev_tail}»\n" if prev_tail else ""
        if is_final:
            final_inst = f"Это финальная часть! Плавно заверши историю и самая последняя строка должна быть строго: «{final_phrase}»."
        else:
            final_inst = "Заверши часть интригующим мостиком к следующему эпизоду. Финальную фразу пока НЕ пиши."

        sc_prompt = scene_tpl.safe_substitute(
            channel_name=channel_name,
            tone=tone,
            language=language,
            part_num=idx,
            parts_count=actual_scenes,
            min_chars=min_chars,
            blueprint=blueprint,
            scene_source=sc_src,
            prev_context=prev_ctx,
            final_instruction=final_inst,
            script_notes=notes_block,
        )

        sc_resp = router.call("llm", {
            "prompt": sc_prompt,
            "temperature": 0.7,
            "max_tokens": 4096,
        })
        sc_text = clean_script_text(sc_resp.get("text", ""))
        generated_scenes.append(sc_text)
        prev_tail = sc_text[-400:].strip() if len(sc_text) >= 400 else sc_text

    full_adapted = "\n\n".join(generated_scenes).strip()
    full_adapted_cleaned = clean_script_text(full_adapted)

    if final_phrase and final_phrase.strip().lower() not in full_adapted_cleaned.lower():
        full_adapted_cleaned = f"{full_adapted_cleaned.rstrip()}\n\n{final_phrase}"

    return {
        "ok": True,
        "script": full_adapted_cleaned,
        "char_count": len(full_adapted_cleaned),
        "source_chars": source_chars,
        "scenes_count": actual_scenes,
    }
