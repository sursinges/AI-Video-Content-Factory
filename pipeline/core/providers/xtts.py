"""XTTS v2 adapter (coqui-tts maintained fork): 17 languages including Czech.
LICENSE NOTE: XTTS v2 model is CPML — NON-COMMERCIAL. Fine for stage-1
personal use (owner decision 2026-09-12); must NOT ship in the stage-2
product. Small-language coverage (cs, hu, ...) is why it's kept."""

import os
from pathlib import Path

from core.providers.router import Provider, ProviderError

_tts_cache: dict = {}


class XttsProvider(Provider):
    adapter = "xtts"

    def _engine(self):
        if "xtts" not in _tts_cache:
            try:
                from TTS.api import TTS
            except ImportError as e:
                raise ProviderError("xtts: package coqui-tts is not installed") from e
            os.environ.setdefault("COQUI_TOS_AGREED", "1")
            _tts_cache["xtts"] = TTS("tts_models/multilingual/multi-dataset/xtts_v2")
        return _tts_cache["xtts"]

    def execute(self, payload: dict) -> dict:
        # payload ref override (voice library selection)
        if payload.get("ref_audio"):
            self.cfg = dict(self.cfg, ref_audio=payload["ref_audio"],
                            ref_text=payload.get("ref_text", self.cfg.get("ref_text", "")))
        out = payload.get("out_path")
        if not out:
            raise ProviderError("xtts: payload must contain out_path")
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        text = (payload.get("text") or "").strip()
        if not text:
            raise ProviderError("xtts: empty text")
        language = payload.get("language") or self.cfg.get("language", "cs")
        speaker_wav = self.cfg.get("ref_audio")
        try:
            tts = self._engine()
            tts.tts_to_file(
                text=text,
                language=language,
                speaker_wav=speaker_wav if speaker_wav and Path(speaker_wav).exists() else None,
                file_path=str(out),
                split_sentences=True,
            )
            import soundfile as sf

            return {"audio_path": str(out), "duration_sec": round(sf.info(out).duration, 2)}
        except ProviderError:
            raise
        except Exception as e:  # noqa: BLE001
            raise ProviderError(f"xtts: {e}") from e
