"""ADD-51/56 follow-up: the UI dictionary must stay healthy (no raw keys in
the RU slot, no Cyrillic leftovers in other locales, no RU clones)."""

import subprocess
import sys
from pathlib import Path


def test_i18n_dict_health():
    script = Path(__file__).resolve().parents[1] / "tools" / "check_i18n.py"
    r = subprocess.run([sys.executable, "-X", "utf8", str(script)],
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stdout or r.stderr
