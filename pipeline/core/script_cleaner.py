"""Script text sanitizer and parser.

Cleans foreign transcripts and custom scripts from:
- Timestamp ranges (e.g. '01:15-01:45', '[01:15 - 01:45]')
- Individual timestamps (e.g. '[01:15]', '01:15:30', '(12:34)')
- Subtitle cues (SRT/VTT sequence numbers, arrows, header tags)
- Speaker tags (e.g. 'Диктор 1:', 'Спикер:', '[Голос за кадром]:')
- Sound / video cues (e.g. '[Музыка]', '[Аплодисменты]', '(кадры хроники)')
- Links and HTML markup
"""

import re


def clean_script_text(text: str) -> str:
    """Clean arbitrary text from timestamps, speaker markers, and cues.
    
    Produces clean, narration-ready text suitable for TTS or LLM adaptation.
    """
    if not text:
        return ""

    lines = text.splitlines()
    cleaned_lines = []
    
    # 1. First pass line-by-line: drop SRT headers, standalone line numbers, and arrow timestamps
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            cleaned_lines.append("")
            continue
            
        # VTT headers and notes
        if stripped.startswith(("WEBVTT", "Kind:", "Language:", "NOTE", "Style:")):
            continue
            
        # SRT / VTT timestamp arrows: 00:01:15,000 --> 00:01:45,000
        if "-->" in stripped:
            # If the preceding line was just a sequence number, remove it
            if cleaned_lines and cleaned_lines[-1].isdigit():
                cleaned_lines.pop()
            continue
            
        # Just an integer (potential subtitle block number) followed by a timestamp in the next line
        if stripped.isdigit() and i + 1 < len(lines) and "-->" in lines[i + 1]:
            continue

        cleaned_lines.append(line)

    text = "\n".join(cleaned_lines)

    # 2. Remove HTML / XML tags (e.g. <font color="...">, <c>, </c>, <i>)
    text = re.sub(r"<[^>]+>", "", text)

    # 3. Remove URLs
    text = re.sub(r"https?://\S+", "", text)

    # 4. Remove timestamp ranges:
    # 01:15-01:45, 01:15 - 01:45, [01:15-01:45], (00:01:15 - 00:01:45)
    text = re.sub(
        r"[\[\(]?\b\d{1,2}:\d{2}(?::\d{2})?(?:[,.]\d{3})?\s*[-–—~]\s*\d{1,2}:\d{2}(?::\d{2})?(?:[,.]\d{3})?\b[\]\)]?",
        "",
        text,
    )

    # 5. Remove single timestamps in brackets/parentheses:
    # [01:15], (01:15:30), [00:01:15,123]
    text = re.sub(
        r"[\[\(]\s*\d{1,2}:\d{2}(?::\d{2})?(?:[,.]\d{3})?\s*[\]\)]",
        "",
        text,
    )

    # 6. Remove standalone timestamps (e.g. 01:15, 01:15:30)
    text = re.sub(
        r"\b\d{1,2}:\d{2}(?::\d{2})?(?:[,.]\d{3})?\b",
        "",
        text,
    )

    # 7. Remove sound/cues in brackets or parentheses:
    cue_words = r"музыка|музыки|звук|звуки|аплодисменты|смех|пауза|вставка|видеоряд|кадры|титры|заставка|music|applause|laughter|sound"
    text = re.sub(
        rf"[\[\(]\s*(?:{cue_words})[^\]\)]*[\]\)]",
        "",
        text,
        flags=re.IGNORECASE,
    )

    # 8. Remove speaker markers at line starts:
    speaker_words = r"диктор|спикер|рассказчик|голос(?:\s+за\s+кадром)?|ведущий|автор|speaker|narrator|host|voice"
    text = re.sub(
        rf"(?m)^\s*[\[\(]?(?:{speaker_words})(?:\s*\d+)?\s*[\]\)]?\s*[:–—]\s*",
        "",
        text,
        flags=re.IGNORECASE,
    )

    # 9. Clean up spacing and punctuation artifacts
    # Remove space before punctuation (e.g. "word , " -> "word, ")
    text = re.sub(r"\s+([,.:;?!])", r"\1", text)

    # 10. Normalize paragraphs
    cleaned_paragraphs = []
    for paragraph in text.split("\n\n"):
        p_lines = [re.sub(r"[ \t]+", " ", l).strip() for l in paragraph.splitlines()]
        p_text = " ".join(l for l in p_lines if l).strip()
        p_text = re.sub(r"^\s*[-–—:]\s*", "", p_text)
        if p_text:
            cleaned_paragraphs.append(p_text)

    return "\n\n".join(cleaned_paragraphs)


def parse_subtitles_file(content: str) -> str:
    """Parse SRT or VTT subtitle file content directly into continuous narrative text."""
    clean = clean_script_text(content)
    # For subtitles, join multiple short cue paragraphs into continuous speech
    paras = [p.strip() for p in clean.split("\n\n") if p.strip()]
    return " ".join(paras)
