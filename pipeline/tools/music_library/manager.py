"""Music library index/scan/pick (see README). Catalog = local mp3/wav/ogg
files in a folder (default models/music/), filename hints the mood."""

import argparse
import json
import random
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parents[1]
INDEX = HERE / "index.json"


def scan(folder: str) -> dict:
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    tracks = []
    for f in sorted(folder.glob("*")):
        if f.suffix.lower() not in (".mp3", ".wav", ".ogg", ".m4a"):
            continue
        mood = f.stem.split("_")[0].lower()
        tracks.append({"path": str(f), "name": f.stem, "mood": mood})
    INDEX.write_text(json.dumps({"folder": str(folder), "tracks": tracks},
                                ensure_ascii=False, indent=2), encoding="utf-8")
    return {"tracks": len(tracks), "index": str(INDEX)}


def pick(mood: str | None = None) -> str | None:
    if not INDEX.exists():
        return None
    tracks = json.loads(INDEX.read_text(encoding="utf-8"))["tracks"]
    if not tracks:
        return None
    if mood:
        matched = [t for t in tracks if mood in t["mood"] or t["mood"] in (mood or "")]
        if matched:
            return random.choice(matched)["path"]
    return random.choice(tracks)["path"]


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sc = sub.add_parser("scan")
    sc.add_argument("--folder", default=str(ROOT / "models" / "music"))
    pk = sub.add_parser("pick")
    pk.add_argument("--mood", default=None)
    a = ap.parse_args()
    if a.cmd == "scan":
        print(scan(a.folder))
    else:
        print(pick(a.mood) or "(библиотека пуста — скачай треки из YouTube Audio Library в models/music/)")
