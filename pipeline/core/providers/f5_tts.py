"""F5-TTS adapter with Russian finetune (owner pick for "live" voice quality,
MIT license — product-safe). Voice = reference audio + its transcript
(few-shot cloning). Config keys:
  ckpt_file, vocab_file   — finetuned model files (local paths)
  ref_audio, ref_text     — 5-12 s reference sample of the narrator voice
Works on 8 GB GPU; text is synthesized per segment, written to out_path."""

from pathlib import Path

from core.providers.router import Provider, ProviderError

_f5_cache: dict = {}


class F5TTSProvider(Provider):
    adapter = "f5_tts"

    def _engine(self):
        if "f5" not in _f5_cache:
            try:
                from f5_tts.api import F5TTS
            except ImportError as e:
                raise ProviderError("f5_tts: package f5-tts is not installed") from e
            ckpt = self.cfg.get("ckpt_file")
            if not ckpt or not Path(ckpt).exists():
                raise ProviderError(f"f5_tts: ckpt_file missing: {ckpt}")
            _f5_cache["f5"] = F5TTS(
                model=self.cfg.get("model_name", "F5TTS_v1_Base"),
                ckpt_file=ckpt,
                vocab_file=self.cfg.get("vocab_file"),
            )
        return _f5_cache["f5"]

    def _reference(self) -> tuple[str, str]:
        ref_audio = self.cfg.get("ref_audio")
        ref_text = self.cfg.get("ref_text") or ""
        if not ref_audio or not Path(ref_audio).exists():
            raise ProviderError(
                "f5_tts: reference voice sample missing — set ref_audio/ref_text "
                "in providers.yaml (a 5-12 s sample of the narrator voice)")
        return ref_audio, ref_text

    def execute(self, payload: dict) -> dict:
        # payload ref override (voice library selection)
        if payload.get("ref_audio"):
            self.cfg = dict(self.cfg, ref_audio=payload["ref_audio"],
                            ref_text=payload.get("ref_text", self.cfg.get("ref_text", "")))
        out = payload.get("out_path")
        if not out:
            raise ProviderError("f5_tts: payload must contain out_path")
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        text = (payload.get("text") or "").strip()
        if not text:
            raise ProviderError("f5_tts: empty text")
        try:
            ref_audio, ref_text = self._reference()
            f5 = self._engine()
            seed = payload.get("seed")
            wav, sr, _spec = f5.infer(
                ref_file=ref_audio, ref_text=ref_text, gen_text=text,
                file_wave=str(out),
                speed=float(self.cfg.get("speed", 0.9)),  # sleep narration: slightly slower
                remove_silence=True,
                seed=int(seed) % 2**31 if seed else None,
            )
            import soundfile as sf
            info = sf.info(out)
            return {"audio_path": str(out), "duration_sec": round(info.duration, 2)}
        except ProviderError:
            raise
        except Exception as e:  # noqa: BLE001
            raise ProviderError(f"f5_tts: {e}") from e
