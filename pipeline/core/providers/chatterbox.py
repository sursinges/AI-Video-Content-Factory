"""Chatterbox Multilingual TTS adapter (owner pick 2026-09-12): MIT license,
23 languages (ru, cs, en, de, ...) — covers small languages like Czech.
Zero-shot voice cloning from payload/config reference sample. Writes
payload["out_path"]; language comes from the episode manifest via payload."""

from pathlib import Path

from core.providers.router import Provider, ProviderError

_model_cache: dict = {}


class ChatterboxProvider(Provider):
    adapter = "chatterbox"

    def _engine(self, language: str):
        key = self.cfg.get("model", "multilingual")
        if key not in _model_cache:
            try:
                from chatterbox.mtl_tts import ChatterboxMultilingualTTS
            except ImportError as e:
                raise ProviderError("chatterbox: package chatterbox-tts is not installed") from e
            import torch

            device = "cuda" if torch.cuda.is_available() else "cpu"
            _model_cache[key] = ChatterboxMultilingualTTS.from_pretrained(device=device)
        return _model_cache[key]

    def execute(self, payload: dict) -> dict:
        # payload ref override (voice library selection)
        if payload.get("ref_audio"):
            self.cfg = dict(self.cfg, ref_audio=payload["ref_audio"],
                            ref_text=payload.get("ref_text", self.cfg.get("ref_text", "")))
        out = payload.get("out_path")
        if not out:
            raise ProviderError("chatterbox: payload must contain out_path")
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        text = (payload.get("text") or "").strip()
        if not text:
            raise ProviderError("chatterbox: empty text")
        try:
            import torchaudio

            model = self._engine(payload.get("language", "ru"))
            ref = self.cfg.get("ref_audio")
            kwargs = {}
            if ref and Path(ref).exists():
                kwargs["audio_prompt_path"] = ref
            # exaggeration/cfg weight tunable in config; defaults are calm
            wav = model.generate(
                text,
                language_id=payload.get("language") or self.cfg.get("language", "ru"),
                exaggeration=float(self.cfg.get("exaggeration", 0.4)),
                cfg_weight=float(self.cfg.get("cfg_weight", 0.7)),
                **kwargs,
            )
            torchaudio.save(out, wav, model.sr)
            import soundfile as sf

            return {"audio_path": str(out), "duration_sec": round(sf.info(out).duration, 2)}
        except ProviderError:
            raise
        except Exception as e:  # noqa: BLE001
            raise ProviderError(f"chatterbox: {e}") from e
