"""Notes plugin — two levels (owner request 2026-09-13):

DEEP  — свободные markdown-заметки в notes/ (роадмапы, тесты, комментарии к
        пресетам/темам/картинкам). Файлы создаёшь как угодно; UI даёт список и
        редактор. Структура только помогает: notes/roadmap.md, notes/tests.md,
        notes/channels/<канал>/*.md, notes/presets/<пресет>.md ...
SHALLOW — быстрые комментарии к сущностям конвейера: уже живут в library.db
        (notes) и видны в Библиотеке; пополняются из UI.

CLI:
    python tools/notes/manager.py list
    python tools/notes/manager.py new roadmap.md
"""

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NOTES = ROOT / "notes"


def _notes_dir(root=None) -> Path:
    """Root override lets the multi-tenant UI scope notes per tenant."""
    return Path(root) if root else NOTES


def list_notes(root=None):
    NOTES = _notes_dir(root)
    if not NOTES.exists():
        return []
    return sorted(str(f.relative_to(NOTES)).replace("\\", "/") for f in NOTES.rglob("*.md"))


def read(rel: str, root=None) -> str:
    NOTES = _notes_dir(root)
    f = (NOTES / rel).resolve()
    if NOTES not in f.parents:
        raise ValueError("путь вне notes/")
    return f.read_text(encoding="utf-8") if f.exists() else ""


def write(rel: str, content: str):
    f = (NOTES / rel).resolve()
    if NOTES not in f.parents:
        raise ValueError("путь вне notes/")
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(content, encoding="utf-8")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    new = sub.add_parser("new"); new.add_argument("rel")
    a = ap.parse_args()
    if a.cmd == "list":
        print("\n".join(list_notes()) or "(заметок нет)")
    else:
        write(a.rel, f"# {a.rel}\n\n")
        print("создано:", a.rel)
