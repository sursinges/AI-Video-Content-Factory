"""Load KEY=VALUE pairs from workspace .env into os.environ (secrets never
enter git: .env is gitignored)."""

import os
from pathlib import Path


def load_env(path: str | Path):
    path = Path(path)
    if not path.exists():
        return False
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'\"")
        if key:
            os.environ[key] = value
    return True
