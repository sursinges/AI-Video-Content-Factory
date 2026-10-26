"""Smallest.ai Waves Lightning TTS adapter (https://smallest.ai).
Writes synthesized audio to payload["out_path"] and returns its path."""

from pathlib import Path

from core.providers.router import Provider, ProviderError


class SmallestAIProvider(Provider):
    adapter = "smallest_ai"

    def execute(self, payload: dict) -> dict:
        if payload.get("out_path") is None:
            raise ProviderError("smallest_ai: payload must contain out_path")
        out_path = Path(payload["out_path"])
        out_path.parent.mkdir(parents=True, exist_ok=True)

        secret = self.secret()
        if not secret:
            raise ProviderError(
                f"smallest_ai: API key '{self.cfg.get('api_key_ref', 'SMALLEST_AI_API_KEY')}' is missing in .env"
            )

        text = payload.get("text", "")
        if not text:
            raise ProviderError("smallest_ai: payload text is empty")

        voice_id = payload.get("voice") or self.cfg.get("voice_id", "magnus")
        output_format = payload.get("format") or self.cfg.get("output_format", "mp3")
        model = payload.get("model") or self.cfg.get("model", "lightning_v3.1")
        speed = float(payload.get("speed") or self.cfg.get("speed", 1.0))
        language = payload.get("language") or self.cfg.get("language", "auto")

        try:
            from smallestai import SmallestAI

            client = SmallestAI(api_key=secret)
            # synthesize_tts streams chunks of audio
            chunks = []
            for chunk in client.waves.synthesize_tts(
                text=text,
                voice_id=voice_id,
                model=model,
                output_format=output_format,
                speed=speed,
                language=language,
            ):
                chunks.append(chunk)

            if not chunks:
                raise ProviderError("smallest_ai: received 0 bytes from TTS stream")

            out_path.write_bytes(b"".join(chunks))
        except ProviderError:
            raise
        except Exception as e:
            err_msg = str(e)
            if "429" in err_msg or "rate" in err_msg.lower():
                raise ProviderError(f"smallest_ai: rate limited: {e}") from e
            raise ProviderError(f"smallest_ai: error generating speech: {e}") from e

        return {"audio_path": str(out_path), "format": output_format}
