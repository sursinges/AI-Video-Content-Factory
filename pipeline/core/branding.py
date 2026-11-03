"""Brand kit helpers shared by the M5 module and the UI cover studio."""

from pathlib import Path

import yaml


def brand_cover_suffix(config_dir: Path | None = None) -> str:
    """Brand kit style keywords appended to cover generation prompts."""
    try:
        base = Path(config_dir) if config_dir else Path(__file__).resolve().parent.parent / "config"
        f = base / "brand_kit.yaml"
        if not f.exists():
            return ""
        data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        parts = [data.get("cover_style") or "", data.get("style_keywords") or ""]
        return (", ".join(p for p in parts if p)).strip(", ")
    except Exception:  # noqa: BLE001 — branding must never break a cover run
        return ""
