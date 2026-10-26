"""Skeleton generation (S1-02): LLM JSON with validation, deterministic mock
in dry-run, one retry, hard failure with clear error after that."""

from core.contracts import Skeleton
from modules.m1_script.prompts import extract_json, render
from modules.m1_script.vars import FORMS


class M1Error(RuntimeError):
    pass


def compute_parts(manifest, profile) -> tuple[int, int, int, int]:
    """Target duration drives BOTH the number of parts and the per-chunk size.
    Fixed 6000-char chunks made short episodes impossible (5 min target
    produced 16 min of audio). Now the chunk shrinks with the target."""
    s = profile.get("script", {})
    cc = s.get("chunk_chars", [6000, 9000])
    max_chunk = cc[1]
    minutes = manifest.target_minutes or s.get("default_target_minutes", 45)
    total_chars = minutes * s.get("chars_per_minute", 1450)
    # number of body ideas from the nominal chunk size, then split the WHOLE
    # duration budget across all parts (intro+final included) — otherwise
    # intro/final each add a full chunk and the episode overshoots 2-3x
    body = max(1, round(total_chars / ((cc[0] + cc[1]) / 2)))
    n_parts = body + 2
    per = total_chars / n_parts
    min_c = max(300, int(per * 0.8))
    max_c = max(min_c + 200, int(per * 1.15))
    return n_parts, body, min_c, max_c


def gen_skeleton(ctx, n_parts: int, body_count: int, min_chars: int, max_chars: int) -> Skeleton:
    from modules.m1_script.vars import base_vars

    if ctx.dry_run:
        return mock_skeleton(ctx.manifest.topic, n_parts, body_count)

    variables = base_vars(ctx.manifest, ctx.profile, min_chars, max_chars) | {
        "number_of_parts": n_parts, "body_parts_count": body_count,
    }
    prompt = render("skeleton.md", variables)
    last_error = ""
    for _ in range(2):  # one retry
        resp = ctx.router.call("llm", {"prompt": prompt, "temperature": 0.8})
        data = extract_json(resp.get("text", ""))
        if data:
            try:
                sk = Skeleton(**data)
            except Exception as e:  # pydantic errors — treat as invalid JSON payload
                last_error = str(e)
                continue
            if len(sk.ideas) != body_count or sk.number_of_parts != n_parts:
                last_error = f"ideas={len(sk.ideas)} (нужно {body_count}), parts={sk.number_of_parts}"
                continue
            return sk
        last_error = "не удалось разобрать JSON скелета"
    raise M1Error(f"Генерация скелета не удалась после ретраев: {last_error}")


_ANGLES = [
    "как всё началось", "почему это сработало именно так", "какую цену заплатили участники",
    "как это изменило устройство мира", "где система дала трещину", "что осталось нерешённым",
    "как это отзывается сегодня", "какой выбор это оставляет каждому из нас",
]


def mock_skeleton(topic: str, n_parts: int, body_count: int) -> Skeleton:
    ideas = [f"{topic} — {_ANGLES[i % len(_ANGLES)]}" for i in range(body_count)]
    anchors = [f"{topic}: напряжение {i + 1} — {a}" for i, a in enumerate(_ANGLES * 2)][:12]
    mid = list(range(2, max(2, n_parts)))
    return Skeleton(
        description=f"MOCK SKELETON — {topic}",
        anchors=anchors,
        chunks_with_examples=mid[:5],
        forms=list(FORMS),
        ideas=ideas,
        forbidden_phrases=["в современном мире", "ни для кого не секрет"],
        self_instructions=["держать плотность, не растекаться", "не раскрывать ответ до финала"],
        number_of_parts=n_parts,
        body_parts_count=body_count,
    )
