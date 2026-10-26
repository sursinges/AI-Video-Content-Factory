"""Fish Audio TTS adapter (https://api.fish.audio). Writes the synthesized
audio to payload["out_path"] and returns its path + duration; the router
caches by prompt, the file persists in runs/."""

import json
from pathlib import Path

import httpx

from core.providers.router import Provider, ProviderError


class FishAudioProvider(Provider):
    adapter = "fish_audio"

    def execute(self, payload: dict) -> dict:
        url = self.cfg.get("base_url", "https://api.fish.audio/v1/tts")
        if payload.get("out_path") is None:
            raise ProviderError("fish_audio: payload must contain out_path")
        out_path = Path(payload["out_path"])
        out_path.parent.mkdir(parents=True, exist_ok=True)

        body: dict = {
            "text": payload["text"],
            "format": payload.get("format", "mp3"),
            "normalize": True,
        }
        if self.cfg.get("reference_id"):
            body["reference_id"] = self.cfg["reference_id"]

        try:
            with httpx.Client(timeout=self.cfg.get("timeout_sec", 180),
                              proxy=self.cfg.get("proxy")) as client:
                resp = client.post(url, json=body, headers={
                    "Authorization": f"Bearer {self.secret()}",
                    "Content-Type": "application/json",
                })
        except httpx.HTTPError as e:
            raise ProviderError(f"fish_audio: network error: {e}") from e
        if resp.status_code == 429:
            err = ProviderError("fish_audio: rate limited")
            err.headers = resp.headers
            raise err
        if resp.status_code >= 400:
            detail = resp.text[:200]
            raise ProviderError(f"fish_audio: HTTP {resp.status_code}: {detail}")

        out_path.write_bytes(resp.content)
        return {"audio_path": str(out_path), "format": body["format"]}
