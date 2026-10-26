"""Machine validator: §17 of the original skeleton guide as code (S1-02).
Returns human-readable issues; empty list = pass."""

import re


META_MARKERS = [
    "я утверждаю", "я поясняю", "я вижу", "я замечаю", "я формулирую",
    "переходим к", "перейдём к", "давайте рассмотрим", "давай рассмотрим",
    "сначала разберём", "важно понимать", "ни для кого не секрет",
    "в современном мире", "пример:", "вывод:", "сцена:", "итак,",
]
STRUCTURE_PHRASES = ["в этом чанке", "в этом фрагменте", "в этой части выпуска"]
OPPOSITION_RE = [re.compile(r"\bне [^,.!?;\n]{2,40}, а\b"), re.compile(r"\bэто не\s+\S+")]
PLURAL_IMPERATIVES = ["напишите", "подпишитесь", "посмотрите", "поставьте лайк", "оцените видео"]


def validate(text: str, *, role: str, form: int, prev_form: int | None,
             min_chars: int, max_chars: int, stop_words: list[str],
             forbidden_phrases: list[str], final_phrase: str,
             channel_name: str, address: str) -> list[str]:
    issues: list[str] = []
    low = text.lower()

    # length (with tolerance)
    if not (min_chars * 0.9 <= len(text) <= max_chars * 1.1):
        issues.append(f"объём {len(text)} знаков вне диапазона {min_chars}–{max_chars}")

    # markup / brackets
    for marker in ("**", "##", "[", "]", "{", "}", "|---"):
        if marker in text:
            issues.append(f"разметка/скобки в тексте: '{marker}'")

    # meta comments and banned phrases
    for m in META_MARKERS:
        if m in low:
            issues.append(f"метакомментарий/шаблонная фраза: «{m}»")
    for p in STRUCTURE_PHRASES:
        if p in low:
            issues.append(f"упоминание технической структуры: «{p}»")

    # profile stop words and skeleton-forbidden phrases
    for w in stop_words:
        if w and w.lower() in low:
            issues.append(f"стоп-слово профиля: «{w}»")
    for p in forbidden_phrases:
        if p and p.lower() in low:
            issues.append(f"запрещённая формулировка темы: «{p}»")

    # opposition pattern "не X, а Y"
    for rx in OPPOSITION_RE:
        found = rx.findall(text)
        if found:
            issues.append(f"противопоставление «не X, а Y»: {found[:2]}")

    # colon rule: only for enumerations; allow digits (timecodes) — flag prose colons
    colons = re.findall(r"[а-яёa-z]:\s+[а-яёa-z]", low)
    if len(colons) > max(3, len(text) // 1500):
        issues.append(f"двоеточия вне перечислений: {len(colons)} шт.")

    # duplicated sentences (exact after normalization)
    sentences = [re.sub(r"\s+", " ", s.strip().lower()) for s in re.split(r"[.!?]\s", text) if len(s.strip()) > 25]
    seen, dups = set(), set()
    for s in sentences:
        if s in seen:
            dups.add(s[:50])
        seen.add(s)
    if dups:
        issues.append(f"повтор предложений: {list(dups)[:2]}")

    # paragraph starts
    paras = [p.strip() for p in text.split("\n\n") if len(p.strip()) > 40]
    if len(paras) >= 4:
        first_words = [p.split()[0].lower() for p in paras]
        most = max(set(first_words), key=first_words.count)
        if first_words.count(most) > len(first_words) * 0.5:
            issues.append(f"более половины абзацев начинаются со слова «{most}»")

    # address consistency
    if address == "ты":
        for imp in PLURAL_IMPERATIVES:
            if imp in low:
                issues.append(f"обращение на «вы» при адресе «ты»: «{imp}»")

    # role-specific
    if role == "intro" and channel_name and channel_name.lower() not in low:
        issues.append(f"во вступлении нет приветствия с названием канала «{channel_name}»")
    if role == "final":
        last_line = text.rstrip().splitlines()[-1].strip() if text.strip() else ""
        if last_line != final_phrase:
            issues.append(f"финал должен заканчиваться строкой «{final_phrase}», сейчас: «{last_line[:40]}»")

    # adjacent chunk form repetition
    if prev_form is not None and form == prev_form and role == "body":
        issues.append(f"форма чанка {form} повторяется в соседнем чанке")

    return issues
