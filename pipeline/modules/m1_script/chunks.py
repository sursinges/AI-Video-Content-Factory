"""Chunk generation (S1-03): first/mid/final prompt chain with prev-chunk
context; deterministic compliant mock text in dry-run."""

import re
from string import Template

from modules.m1_script.prompts import render
from modules.m1_script.vars import part_role


def clean_text(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```[a-z]*\n?|```$", "", text, flags=re.MULTILINE).strip()
    text = re.sub(r'^"(.*)"$', r"\1", text, flags=re.S).strip()
    return text


def gen_chunk(ctx, sk, part: int, prev_text: str | None = None, issues: list[str] | None = None) -> str:
    from modules.m1_script.vars import base_vars, skeleton_to_text

    profile = ctx.profile
    s = profile.get("script", {})
    cc = s.get("chunk_chars", [6000, 9000])
    min_chars, max_chars = cc
    n = sk.number_of_parts
    role = part_role(part, n)
    base = base_vars(ctx.manifest, profile, min_chars, max_chars)

    examples_rule = ("В этом чанке допустим один микропример (1–2 предложения), без ярлыков."
                     if part in sk.chunks_with_examples
                     else "В этом чанке примеры запрещены — фокус на логике и концептуальном раскрытии.")

    extra = ""
    if issues:
        extra = ("ПРЕДЫДУЩАЯ ПОПЫТКА НЕ ПРОШЛА ПРОВЕРКУ. Исправь ровно эти замечания, "
                 "не меняя удачное:\n" + "\n".join(f"— {i}" for i in issues))

    variables = base | {
        "number_of_parts": n,
        "part_number": part,
        "prev_part_number": max(1, part - 1),
        "part_idea": (sk.ideas[part - 2] if role == "body" else base["topic"]),
        "chunk_form": sk.forms[min(part - 1, len(sk.forms) - 1)],
        "examples_rule": examples_rule,
        "previous_text": (prev_text or "")[-4000:],
        "skeleton": skeleton_to_text(sk),
        "extra": extra,
    }

    if ctx.dry_run:
        return mock_text(ctx, role, part, min_chars)

    name = "chunk_first.md" if role == "intro" else "chunk_final.md" if role == "final" else "chunk_mid.md"
    resp = ctx.router.call("llm", {"prompt": render(name, variables), "temperature": 0.9})
    return clean_text(resp.get("text", ""))


# --- deterministic mock text (dry-run only) ----------------------------------

_T = [
    "Спокойный вечер под номером {i} располагает к историям, где время течёт медленно и детали складываются в целую эпоху",
    "Наблюдая за решениями героев эпизода {i}, начинаешь видеть, как малый выбор оборачивается большими последствиями",
    "Свидетельства той поры {i} сохранили противоречия, каждое из которых добавляет картине глубины",
    "Между событиями фрагмента {i} всегда есть промежуток, где очевидным решение становится лишь десятилетия спустя",
    "Цена просчёта в этих обстоятельствах {i} измерялась годами и репутацией целых семей",
    "Когда дневной шум эпизода {i} стихает, такие истории слышатся совсем иначе",
    "В архивах той эпохи {i} отыскались письма, меняющие привычное прочтение знакомых событий",
    "За каждым громким решением той главы {i} стояла долгая тень несбывшихся вариантов",
    "Отголоски тех решений главы {i} доходят до наших дней почти без изменений",
]


def mock_text(ctx, role: str, part: int, min_chars: int) -> str:
    """Deterministic, validator-compliant text for dry-runs and tests."""
    profile = ctx.profile
    s = profile.get("script", {})
    final_phrase = profile.get("final_phrase", "Спокойной ночи.")
    greeting = Template(s.get("greeting_formula", "Привет. Ты на канале $channel_name")).safe_substitute(
        {"channel_name": profile.get("name", "канал")})

    def body_block(target_len: int) -> str:
        paras, k = [], 0
        total = 0
        while total < target_len:
            para = " ".join(
                _T[(k + j) % len(_T)].format(i=k + j) for j in range(3)
            ) + "."
            paras.append(para)
            total += len(para) + 2
            k += 3
        return "\n\n".join(paras)

    opener = f"Раздел истории номер {part} продолжает общее повествование без спешки.\n\n"

    if role == "intro":
        head = (f"{greeting}. Сегодня расскажу об истории, которую стоит услышать неспешно. "
                "Речь пойдёт о том, как одно решение прошлого до сих пор меняет жизни многих людей. "
                "А ты замечал, как редко вспоминают о событиях, определивших целые эпохи? "
                "Если проект тебе близок, поддержка в описании поможет ему выходить чаще.\n\n")
        return head + body_block(min_chars)

    if role == "final":
        core = body_block(min_chars)
        close = ("\n\nЭта история возвращает нас к началу — к вопросу, оставленному без ответа. "
                 "Слушая её сегодня, каждый решает сам, чей выбор был верным.\n"
                 + final_phrase)
        return opener + core + close

    return opener + body_block(min_chars)
