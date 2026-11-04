"""VoiceStudio (debpalash/VoiceStudio, AGPL-3.0) local TTS adapter.

Integrates through VoiceStudio's documented OpenAI-compatible HTTP endpoint
(POST /v1/audio/speech, port 3900, Bearer OMNIVOICE_API_KEY) — the pipeline
talks to it over the API only, no code is linked in (license boundary).
Runs on the user's machine next to the Desktop edition; voice cloning is
done in the VoiceStudio app itself and referenced here by voice/profile id
(only clone voices you have the rights to).
"""

from pathlib import Path

import httpx

from core.providers.router import Provider, ProviderError


class VoiceStudioProvider(Provider):
    adapter = "voice_studio"

    def execute(self, payload: dict) -> dict:
        out_path = payload.get("out_path")
        if not out_path:
            raise ProviderError("voice_studio: payload must contain out_path")
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        text = payload.get("text", "")
        if not text:
            raise ProviderError("voice_studio: payload text is empty")

        base = str(self.cfg.get("base_url", "http://127.0.0.1:3900")).rstrip("/")
        key = self.secret()
        if not key:
            raise ProviderError(
                f"voice_studio: API key '{self.cfg.get('api_key_ref', 'VOICESTUDIO_API_KEY')}' "
                "is missing in .env (the key VoiceStudio generates in its settings)"
            )
        model = payload.get("model") or self.cfg.get("model", "default")
        voice = payload.get("voice") or self.cfg.get("voice", "alloy")
        response_format = payload.get("format") or self.cfg.get("response_format", "wav")
        timeout = float(self.cfg.get("timeout_sec", 300))

        try:
            r = httpx.post(
                f"{base}/v1/audio/speech",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={"model": model, "voice": voice, "input": text,
                      "response_format": response_format},
                timeout=timeout,
            )
            if r.status_code == 401:
                raise ProviderError("voice_studio: unauthorized — check VOICESTUDIO_API_KEY")
            if r.status_code == 404:
                raise ProviderError(
                    "voice_studio: /v1/audio/speech not found — is the VoiceStudio "
                    "backend running (port 3900) with the production API enabled?")
            r.raise_for_status()
            audio = r.content
            if not audio:
                raise ProviderError("voice_studio: received 0 bytes from TTS")
            out_path.write_bytes(audio)
        except ProviderError:
            raise
        except Exception as e:  # noqa: BLE001 — surface as provider error
            msg = str(e)
            if "429" in msg or "rate" in msg.lower():
                raise ProviderError(f"voice_studio: rate limited: {e}") from e
            if "connect" in msg.lower():
                raise ProviderError(
                    f"voice_studio: cannot reach backend at {base} — start VoiceStudio first") from e
            raise ProviderError(f"voice_studio: error generating speech: {e}") from e

        return {"audio_path": str(out_path), "format": response_format}
