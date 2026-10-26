"""Jamendo Music adapter: open CC-licensed catalog with a free API
(client_id from devportal.jamendo.com, instant registration). Searches by
mood/keywords, picks a track long enough for the episode, downloads mp3.
License: Jamendo tracks are CC — attribution requirements vary per track."""

from pathlib import Path

from core.providers.router import Provider, ProviderError

API = "https://api.jamendo.com/v3.0/tracks/"


class JamendoMusicProvider(Provider):
    adapter = "jamendo_music"

    def execute(self, payload: dict) -> dict:
        out = payload.get("out_path")
        if not out:
            raise ProviderError("jamendo_music: payload must contain out_path")
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        client_id = self.secret()
        if not client_id:
            raise ProviderError(
                "jamendo_music: нет client_id — бесплатная регистрация на "
                "devportal.jamendo.com, ключ в .env как JAMENDO_CLIENT_ID "
                "(api_key_ref: JAMENDO_CLIENT_ID в providers.yaml)")
        import httpx

        q = payload.get("mood") or self.cfg.get("default_query") or "calm ambient"
        need = int(payload.get("min_duration_sec", 180))
        try:
            with httpx.Client(timeout=60) as client:
                r = client.get(API, params={
                    "client_id": client_id, "format": "json", "search": q,
                    "audioformat": "mp32", "include": "musicinfo",
                    "duration_between": f"{need}_1200", "limit": 10})
                r.raise_for_status()
                results = r.json().get("results", [])
                if not results:
                    r = client.get(API, params={
                        "client_id": client_id, "format": "json", "search": q,
                        "audioformat": "mp32", "limit": 10})
                    results = r.json().get("results", [])
                if not results:
                    raise ProviderError(f"jamendo_music: ничего по «{q}»")
                track = results[0]
                audio = client.get(track["audio"], timeout=180).content
                out = Path(out).with_suffix(".mp3")
                out.write_bytes(audio)
                return {"audio_path": str(out), "name": track.get("name", ""),
                        "duration_sec": track.get("duration")}
        except ProviderError:
            raise
        except Exception as e:  # noqa: BLE001
            raise ProviderError(f"jamendo_music: {e}") from e
