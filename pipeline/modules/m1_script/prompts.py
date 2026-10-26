"""Prompt loading/rendering (S1-01). Prompt files use $var placeholders
(string.Template) because prompts contain JSON braces; leading single-#
lines are meta comments for the pipeline and are stripped before sending."""

import re
from pathlib import Path
from string import Template

PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"


def render(name: str, variables: dict) -> str:
    text = (PROMPTS_DIR / name).read_text(encoding="utf-8")
    return _strip_meta(Template(text).safe_substitute(variables))


def _strip_meta(text: str) -> str:
    lines = text.splitlines()
    i = 0
    while i < len(lines) and re.match(r"^#($|\s)", lines[i]):
        i += 1
    return "\n".join(lines[i:]).strip()


def extract_json(text: str) -> dict | None:
    """First balanced {...} block parsed as JSON; None on any failure so the
    caller can fall back gracefully (mock providers don't speak JSON)."""
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start : i + 1])
                except json.JSONDecodeError:
                    return None
    return None


import json  # noqa: E402  (used by extract_json above)
