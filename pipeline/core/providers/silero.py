"""Local Silero TTS adapter (owner decision 2026-09-12): Russian voices,
MIT license — safe for the future product. v4 model, 48 kHz; long texts are
split by sentences; writes payload["out_path"] (wav)."""

import re
from pathlib import Path

from core.providers.router import Provider, ProviderError

_model_cache: dict = {}


class SileroProvider(Provider):
    adapter = "silero"

    def _model(self):
        import torch

        key = self.cfg.get("model_id", "v4_ru")
        if key not in _model_cache:
            model, _ = torch.hub.load(
                "snakers4/silero-models", "silero_tts",
                language="ru", speaker=key, trust_repo=True)
            device = "cuda" if torch.cuda.is_available() else "cpu"
            model.to(device)  # torch.package model: .to() returns None — keep the object
            _model_cache[key] = (model, device)
        return _model_cache[key]

    def execute(self, payload: dict) -> dict:
        out = payload.get("out_path")
        if not out:
            raise ProviderError("silero: payload must contain out_path")
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        text = (payload.get("text") or "").strip()
        if not text:
            raise ProviderError("silero: empty text")
        try:
            import soundfile as sf
            import torch

            model, device = self._model()
            speaker = self.cfg.get("speaker", "eugene")
            rate = 48000

            # Silero handles limited text length at once — split by sentences
            sentences = re.split(r"(?<=[.!?…])\s+", text)
            chunks, cur = [], ""
            for s in sentences:
                if cur and len(cur) + len(s) > 900:
                    chunks.append(cur.strip())
                    cur = s
                else:
                    cur = f"{cur} {s}".strip()
            if cur:
                chunks.append(cur)

            parts = []
            for chunk in chunks:
                audio = model.apply_tts(text=chunk, speaker=speaker,
                                        sample_rate=rate, put_accent=True,
                                        put_yo=True)
                parts.append(audio.cpu())
            audio = torch.cat(parts)
            sf.write(out, audio.numpy(), rate)
            return {"audio_path": str(out), "duration_sec": round(len(audio) / rate, 2)}
        except ProviderError:
            raise
        except Exception as e:  # noqa: BLE001
            raise ProviderError(f"silero: {e}") from e
