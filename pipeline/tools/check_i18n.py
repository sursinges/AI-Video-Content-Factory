#!/usr/bin/env python3
"""i18n health check for pipeline/ui/static/index.html (ADD-51/56 follow-up).

Finds:
  1. dotted keys whose RU slot (index 0) is the raw key — RU users see them
  2. locale slots that are identical clones of the RU string (index > 0)
  3. Cyrillic text sitting in non-RU locale slots (wrong-language leftovers,
     e.g. Ukrainian in the ar slot)

Usage:  python tools/check_i18n.py   (run from anywhere; paths are module-relative)
Exit code: 0 if clean, 1 if findings (usable in CI / the verify-task skill).
"""

import json
import re
import sys
from pathlib import Path

FILE = Path(__file__).resolve().parents[1] / "ui" / "static" / "index.html"
LANG_ORDER = ["ru", "en", "es", "zh", "hi", "ar", "pt", "fr", "de", "ja"]

CIRR = re.compile(r"[\u0400-\u04FF]")
# Devanagari/CJK/Arabic helpers to distinguish "intentionally same" brand names
HAS_NON_LATIN = re.compile(r"[\u0400-\u04FF\u0600-\u06FF\u0900-\u097F\u4E00-\u9FFF\u3040-\u30FF]")


def extract_dict_entries(text: str) -> list[tuple[str, list[str]]]:
    entries = []
    for m in re.finditer(r'(?:\s*)(?:"((?:[^"\\]|\\.)+)"|\'((?:[^\'\\]|\\.)+)\'):\s*\[', text):
        key = m.group(1) if m.group(1) is not None else m.group(2)
        # find the matching closing bracket of this array
        i = m.end() - 1
        depth, j = 0, i
        while j < len(text):
            if text[j] == "[":
                depth += 1
            elif text[j] == "]":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        raw = text[i:j + 1]
        try:
            vals = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(vals, list) and len(vals) == len(LANG_ORDER) and all(isinstance(v, str) for v in vals):
            entries.append((key, vals))
    return entries


def is_brand_clone(key: str, ru: str, other: str) -> bool:
    """Same-string slots are legitimate for latin product/brand names
    ("Dark History (Cinematic 35mm)", provider names, etc.)."""
    if ru != other:
        return False
    return not CIRR.search(ru)


def main() -> int:
    text = FILE.read_text(encoding="utf-8")
    findings = []
    for key, vals in extract_dict_entries(text):
        dotted_key = bool(re.match(r"^[a-zA-Z0-9_.]+$", key)) and "." in key
        if dotted_key:
            if vals[0] == key:
                findings.append(f"RU slot holds the raw key ({key})")
            continue  # dotted keys: RU slot is the only issue
        for idx, v in enumerate(vals[1:], start=1):
            if v == vals[0] and len(vals[0]) > 3 and not is_brand_clone(key, vals[0], v):
                findings.append(f"slot {LANG_ORDER[idx]} clones the RU string ({key[:40]}…)")
            elif CIRR.search(v):
                findings.append(f"slot {LANG_ORDER[idx]} has Cyrillic ({key[:40]}…): {v[:40]}")

    if findings:
        print(f"i18n: {len(findings)} finding(s) in {FILE.name}")
        for f in findings:
            print(" -", f)
        return 1
    print("i18n: clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
