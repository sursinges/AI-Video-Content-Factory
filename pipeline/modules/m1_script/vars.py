"""Shared M1 helpers: profile-driven variables for prompt rendering."""

from string import Template

from core.contracts import EpisodeManifest


def base_vars(manifest: EpisodeManifest, profile: dict, min_chars: int, max_chars: int) -> dict:
    s = profile.get("script", {})
    channel_name = profile.get("name", "канал")
    stop_words = list(profile.get("stop_words", [])) + list(s.get("stop_words_extra", []))
    notes = (getattr(manifest, "script_notes", None) or "").strip()
    notes_formatted = f"\n\n## Особые пометки и пожелания автора (длительность, акценты, детали):\n{notes}\n" if notes else ""
    return {
        "topic": manifest.topic,
        "language": manifest.language,
        "channel_name": channel_name,
        "channel_description": (profile.get("description") or "").strip(),
        "tone": profile.get("tone", "спокойный, разговорный"),
        "address_rule": 'на «ты», к одному слушателю' if profile.get("address", "ты") == "ты"
                        else 'на «вы», к аудитории',
        "narrator_rule": profile.get("narrator_person", "первое лицо, эпизодически"),
        "final_phrase": profile.get("final_phrase", "Спокойной ночи."),
        "stop_words": ", ".join(f"«{w}»" for w in stop_words),
        "forbidden_self_names": ", ".join(f"«{n}»" for n in s.get("forbidden_self_names", [])),
        "cta_rule": s.get("cta_rule", "без агрессивного CTA"),
        "escalation_principle": s.get("escalation_principle", "от частного к общему"),
        "greeting_formula": Template(s.get("greeting_formula", "Привет. Ты на канале $channel_name"))
                            .safe_substitute({"channel_name": channel_name}),
        "audience": s.get("audience", "обыватели"),
        "explanation_style": s.get("explanation_style", "простыми словами и аналогиями"),
        "min_characters": min_chars,
        "max_characters": max_chars,
        "intro_length_min": int(min_chars * 0.5),
        "intro_length_max": int(max_chars * 0.8),
        "min_total_characters": min_chars * 3,
        "address": profile.get("address", "ты"),
        "script_notes": notes_formatted,
    }


FORMS = [
    "утверждение → сдвиг определения → ключевой insight → следствие → неразрешённая граница",
    "общее допущение → опровержение → пример/кейс → осложнение → принцип перехода",
    "вопрос → напряжение → insight → цена/последствия → частичное разрешение",
    "два возможных следствия → напряжение между ними → граница объяснения → цена вопроса → частичное разрешение",
    "парадокс → явное называние парадокса → попытка разрешения → почему простое разрешение невозможно → следствие для практики",
    "масштаб претензии → сужение к конкретному случаю → разрыв между ними → что это означает системно → открытый вопрос",
    "историческое или концептуальное противопоставление → точка пересечения → что остаётся нерешённым → актуальность для настоящего",
    "малое наблюдение → расширение до структурного принципа → проверка принципа на пределе → где принцип ломается → принцип перехода",
]


def part_role(part: int, number_of_parts: int) -> str:
    if part == 1:
        return "intro"
    if part == number_of_parts and number_of_parts > 1:
        return "final"
    return "body"


def pick_form(part: int, role: str, number_of_parts: int) -> int:
    if role == "intro":
        return 1
    if role == "final":
        return 8
    # cycle 2..7 so adjacent body chunks never share a form
    idx = (part - 2) % 6 + 2
    return idx


def skeleton_to_text(sk) -> str:
    lines = [f"ОПИСАНИЕ: {sk.description}", "", "ЯКОРЯ:"]
    lines += [f"— {a}" for a in sk.anchors]
    lines += ["", "ИДЕИ ОСНОВНОГО БЛОКА (по одной на часть):"]
    lines += [f"{i + 2}. {idea}" for i, idea in enumerate(sk.ideas)]
    lines += ["", "ФОРМЫ ЧАНКОВ:"]
    lines += [f"{i + 1}: {f}" for i, f in enumerate(sk.forms)]
    lines += ["", f"ЧАНКИ С ПРИМЕРАМИ: {', '.join(map(str, sk.chunks_with_examples)) or 'нет'}"]
    if sk.self_instructions:
        lines += ["", "ПРАВИЛА ГЕНЕРАЦИИ:"]
        lines += [f"— {r}" for r in sk.self_instructions]
    return "\n".join(lines)
