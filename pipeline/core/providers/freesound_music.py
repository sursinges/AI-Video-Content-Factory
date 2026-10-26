"""Freesound adapter: CC / CC0 catalog with a free API token
(freesound.org, instant registration -> .env FREESOUND_TOKEN). Searches by
mood keywords and downloads the HQ MP3 preview (previews are public, the full
original needs OAuth — for a background bed the 128k preview is enough).
License info is returned per track; verify attribution per track license."""

from pathlib import Path

from core.providers.router import Provider, ProviderError

API = "https://freesound.org/apiv2/search/text/"

KEYWORDS = {
    "night": "calm ambient night drone",
    "rain": "rain soundscape ambience",
    "wind": "wind gusts ambience",
    "drone": "dark ambient drone pad",
    "fire": "fire crackling campfire ambience",
    "space": "space ambient pad atmospheric",
}


class FreesoundMusicProvider(Provider):
    adapter = "freesound_music"

    def execute(self, payload: dict) -> dict:
        out = payload.get("out_path")
        if not out:
            raise ProviderError("freesound_music: payload must contain out_path")
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        token = self.secret()
        if not token:
            raise ProviderError(
                "freesound_music: нет токена — бесплатная регистрация на "
                "freesound.org/api/apply, ключ в .env как FREESOUND_TOKEN "
                "(api_key_ref: FREESOUND_TOKEN в providers.yaml)")
        import httpx

        mood = (payload.get("mood") or "night").lower()
        q = KEYWORDS.get(mood, mood or "calm ambient")
        # cfg override for stricter licensing, e.g. 'license:"Creative Commons 0"'
        lic_filter = self.cfg.get("license_filter", "")
        filt = "duration:[45 TO 3600]"
        if lic_filter:
            filt += " " + lic_filter
        try:
            with httpx.Client(timeout=60) as client:
                r = client.get(API, params={
                    "query": q, "token": token, "filter": filt,
                    "page_size": 10,
                    "fields": "id,name,previews,license,duration,username"})
                r.raise_for_status()
                results = r.json().get("results", [])
                if not results:
                    raise ProviderError(f"freesound_music: ничего по «{q}»")
                for item in results:
                    previews = item.get("previews") or {}
                    url = previews.get("preview-hq-mp3")
                    if not url:
                        continue
                    dl = client.get(url, timeout=180)
                    if dl.status_code != 200 or len(dl.content) < 100_000:
                        continue
                    Path(out).with_suffix(".mp3").write_bytes(dl.content)
                    return {"audio_path": str(Path(out).with_suffix(".mp3")),
                            "name": item.get("name", ""),
                            "license": item.get("license", ""),
                            "creator": item.get("username", "")}
                raise ProviderError("freesound_music: у результатов нет MP3-превью")
        except ProviderError:
            raise
        except Exception as e:  # noqa: BLE001
            raise ProviderError(f"freesound_music: {e}") from e
