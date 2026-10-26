"""Openverse (WordPress) CC-audio search — keyless anonymous API.

Searches Creative-Commons / CC0 audio by mood keywords and downloads the first
working result as the ambient bed. External service: needs internet at render
time; falls back to error so the router chain can try the next music provider.
"""

from pathlib import Path

import httpx

from core.providers.router import Provider, ProviderError

KEYWORDS = {
    "night": "calm ambient night drone",
    "rain": "rain soundscape",
    "wind": "wind ambience",
    "drone": "dark ambient drone",
    "fire": "fire crackling ambience",
    "space": "space ambient pad",
}


class OpenverseMusicProvider(Provider):
    adapter = "openverse_music"

    def execute(self, payload: dict) -> dict:
        out = payload.get("out_path")
        if not out:
            raise ProviderError("openverse_music: payload must contain out_path")
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        mood = (payload.get("mood") or "night").lower()
        kw = KEYWORDS.get(mood, "ambient")
        try:
            r = httpx.get(
                "https://api.openverse.org/v1/audio/",
                params={"q": kw, "page_size": 12},
                timeout=30,
                headers={"User-Agent": "pipeline-ui/1.0 (local video pipeline)"},
            )
            r.raise_for_status()
            results = r.json().get("results", [])
        except Exception as e:  # noqa: BLE001
            raise ProviderError(f"openverse: поиск не удался — {e}") from e

        for item in results:
            url = item.get("url") or item.get("alt_files")
            if isinstance(url, list) and url:
                url = url[0] if isinstance(url[0], str) else (url[0] or {}).get("url")
            if not url:
                continue
            try:
                dl = httpx.get(url, timeout=180, follow_redirects=True,
                               headers={"User-Agent": "pipeline-ui/1.0"})
                if dl.status_code != 200 or len(dl.content) < 100_000:
                    continue
                Path(out).write_bytes(dl.content)
                return {"audio_path": str(out), "source": item.get("url"),
                        "license": item.get("license"), "creator": item.get("creator")}
            except Exception:  # noqa: BLE001 — пробуем следующий результат
                continue
        raise ProviderError("openverse: подходящих треков не нашлось — попробуй library_music или ambient_synth")
