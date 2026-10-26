"""M2 audio module (S2): emotional tags -> segmentation -> TTS -> concat ->
(faster-whisper | fallback) word timings -> subtitles + SRT."""

import json
import re
import subprocess
import os
from pathlib import Path

from core.contracts import (AudioResult, FactCheck, Script, SpeechPlan,
                            SubLine, Subtitles, TtsSegment, Word)
from core.media import concat_audio, ffprobe_duration, synth_silence, write_srt
from modules.base import Artifact, Module, RunContext
from modules.m1_script.prompts import extract_json, render

_TAG_RE = re.compile(r"\[[^\]]*\]")


def strip_tags(text: str) -> str:
    return _TAG_RE.sub("", text).strip()


def apply_pronunciation(text: str, prof: dict) -> str:
    """Owner's pronunciation dictionary (ViralMint-style): word -> replacement,
    applied just before TTS (stress fixes, brand names, acronyms)."""
    pmap = (prof.get("tts") or {}).get("pronunciation_map") or {}
    for wrong, right in pmap.items():
        text = text.replace(wrong, right)
    return text


def segment_text(text: str, max_chars: int) -> list[str]:
    """Split into sentence groups no longer than max_chars."""
    sentences = re.split(r"(?<=[.!?…])\s+", text.replace("\n", " ").strip())
    segs, cur = [], ""
    for s in sentences:
        if cur and len(cur) + len(s) + 1 > max_chars:
            segs.append(cur.strip())
            cur = s
        else:
            cur = f"{cur} {s}".strip()
    if cur.strip():
        segs.append(cur.strip())
    return segs


_whisper_model = None
_whisper_device = None


def _whisper_words(path: str, language: str) -> list[tuple[str, float, float]]:
    global _whisper_model, _whisper_device
    from faster_whisper import WhisperModel
    if _whisper_model is None:
        # TUNE-03: try CUDA first (GPU whisper is several times faster); fall
        # back to CPU int8 when cuDNN/cublas DLLs are missing. Cached per device.
        device = os.environ.get("WHISPER_DEVICE", "auto")
        cuda_ok = False
        if device in ("auto", "cuda"):
            try:
                # gate on a WORKING torch CUDA (chatterbox runs on it here);
                # ctranslate2's own cuda init can HANG when cuDNN is broken —
                # never attempt it blindly (a hang, not an exception).
                import torch

                cuda_ok = torch.cuda.is_available()
            except Exception:  # noqa: BLE001
                cuda_ok = False
        if cuda_ok:
            _whisper_model = WhisperModel("small", device="cuda", compute_type="float16")
            _whisper_device = "cuda"
        else:
            _whisper_model = WhisperModel("small", device="cpu", compute_type="int8")
            _whisper_device = "cpu"

    if _whisper_model is None:
        # CPU int8 for now; switch to device="cuda", compute_type="float16"
        # on the 3070 Ti once cuDNN DLLs are in place (S2 polish).
        _whisper_model = WhisperModel("small", device="cpu", compute_type="int8")
    segments, _info = _whisper_model.transcribe(path, language=language, word_timestamps=True)
    return [(w.word.strip(), w.start, w.end)
            for seg in segments for w in (seg.words or []) if w.word.strip()]


def _fallback_words(text: str, duration: float, part: int, offset: float = 0.0) -> list[Word]:
    """Proportional timings when whisper is unavailable (documented in AudioResult)."""
    words = [w for w in text.split() if w]
    weights = [max(len(w), 2) for w in words]
    total = sum(weights) or 1
    out, t = [], offset
    for w, wt in zip(words, weights):
        d = duration * wt / total
        out.append(Word(w=w, start=round(t, 3), end=round(min(t + d, offset + duration), 3), part=part))
        t += d
    return out


class M2Audio(Module):
    name = "m2_audio"

    def run(self, ctx: RunContext) -> list[Artifact]:
        script = Script(**json.loads(
            (ctx.run_dir / "script" / "script.json").read_text(encoding="utf-8")))
        tts_cfg = ctx.profile.get("tts", {})
        seg_max = int(tts_cfg.get("segment_chars", [200, 500])[1])
        pause = float(tts_cfg.get("pause_between_parts_sec", 1.5))
        language = ctx.manifest.language
        # language map: small languages may need a different engine than the
        # default one (e.g. cs -> xtts, ru -> chatterbox)
        provider = (tts_cfg.get("language_map") or {}).get(language)             or ctx.router.defaults.get("tts", "mock")
        voice_id = (ctx.profile.get("voice") or {}).get("voice_id") or "default"

        # DRAFT PLAN (P5 preview): no synthesis at all — estimate part durations
        # from text length (~14.5 chars/sec) and build proportional word/line
        # timings so the scene plan can be previewed without rendering. The real
        # render resets m2/m3 steps and re-runs them with synthesis.
        if ctx.profile.get("draft_plan"):
            cps = 14.5
            d_words: list[Word] = []
            d_offset = 0.0
            d_parts: list[float] = []
            for chunk in script.chunks:
                text = strip_tags(chunk.text)
                dur = max(3.0, len(text) / cps)
                d_parts.append(round(dur, 2))
                d_words.extend(_fallback_words(text, dur, chunk.part, offset=d_offset))
                d_offset += dur + pause
            d_lines: list[SubLine] = []
            cur_w, cur_start = [], None
            for w in d_words:
                if cur_start is None:
                    cur_start = w.start
                cur_w.append(w.w)
                if len(" ".join(cur_w)) >= 42 or w.end - cur_start >= 3.0:
                    d_lines.append(SubLine(text=" ".join(cur_w), start=cur_start, end=w.end, part=w.part))
                    cur_w, cur_start = [], None
            if cur_w:
                d_lines.append(SubLine(text=" ".join(cur_w), start=cur_start or 0.0,
                                       end=d_words[-1].end, part=d_words[-1].part))
            (ctx.run_dir / "subtitles").mkdir(parents=True, exist_ok=True)
            subs = Subtitles(words=d_words, lines=d_lines)
            write_srt([l.model_dump() for l in d_lines], ctx.run_dir / "subtitles" / "subtitles.srt")
            ctx.router.on_event("m2_audio DRAFT: timings estimated from text length, no synthesis")
            result = AudioResult(episode_path=None, duration_sec=round(max(d_offset - pause, 0.0), 2),
                                 parts=d_parts, engine="draft", tts_provider="draft")
            plan = SpeechPlan(provider="draft", voice_id="draft", model="draft",
                              segments=[TtsSegment(part=1, text_with_tags="[draft]", char_count=7)])
            return [("audio/speechplan.json", plan),
                    ("subtitles/subtitles.json", subs),
                    ("audio/audio_result.json", result)]

        # 1) emotional tags (LLM; skipped in dry-run — mock text stays as is)
        tagged: dict[int, str] = {}
        for chunk in script.chunks:
            if ctx.dry_run:
                tagged[chunk.part] = chunk.text
                continue
            try:
                resp = ctx.router.call("llm", {"prompt": render("tags_tts.md", {
                    "chunk_text": chunk.text, "stop_tags": "крик, возбуждение"}), "temperature": 0.3})
                data = extract_json(resp.get("text", ""))
                tagged[chunk.part] = (data or {}).get("text") or chunk.text
            except Exception as e:
                ctx.router.on_event(f"m2_audio tags_tts notice: {e}, using untagged text")
                tagged[chunk.part] = chunk.text

        # 2) segmentation
        plan_segments: list[TtsSegment] = []
        seg_texts: dict[int, list[str]] = {}
        for part, text in tagged.items():
            segs = segment_text(text, seg_max) or [text]
            seg_texts[part] = segs
            plan_segments += [TtsSegment(part=part, text_with_tags=s, char_count=len(s)) for s in segs]
        plan = SpeechPlan(provider=provider, voice_id=voice_id, model="tts", segments=plan_segments)

        # 3) TTS per segment (provider writes files; cached by router)
        audio_dir = ctx.run_dir / "audio"
        files: dict[int, list[str]] = {p: [] for p in tagged}
        for seg in plan.segments:
            out = audio_dir / f"p{seg.part:02d}" / f"s{len(files[seg.part]):03d}.mp3"
            res = ctx.router.call("tts", {"text": apply_pronunciation(strip_tags(seg.text_with_tags), tts_cfg),
                                          "out_path": str(out), "format": "mp3",
                                          "language": language})
            files[seg.part].append(res["audio_path"])

        # 4) per-part concat + silence between parts + full episode wav
        silence = audio_dir / "_pause.mp3"
        synth_silence(silence, pause)
        part_wavs, part_durations = [], []
        for part, flist in files.items():
            pw = audio_dir / f"part_{part:02d}.wav"
            concat_audio(flist + [silence], pw)
            part_wavs.append(pw)
            part_durations.append(ffprobe_duration(pw))
        episode = audio_dir / "episode.wav"
        concat_audio(part_wavs, episode)
        duration = ffprobe_duration(episode)

        # 5) word timings: faster-whisper per part, fallback proportional.
        # whisper timestamps are per-part-file — shift by cumulative part offset!
        engine = "whisper"
        words: list[Word] = []
        offset = 0.0
        for part, pw in zip(tagged, part_wavs):
            p_dur = part_durations[part - 1]
            try:
                part_words = [
                    Word(w=w, start=round(s + offset, 3), end=round(e + offset, 3), part=part)
                    for w, s, e in _whisper_words(str(pw), language)
                ]
                if part_words:
                    words.extend(part_words)
                else:
                    words.extend(_fallback_words(strip_tags(tagged[part]), p_dur, part, offset=offset))
                    engine = "fallback"
            except Exception as e:
                ctx.router.on_event(f"m2_audio whisper notice on part {part}: {e}, using proportional fallback")
                words.extend(_fallback_words(strip_tags(tagged[part]), p_dur, part, offset=offset))
                engine = "fallback"
            offset += p_dur

        # 6) subtitle lines: <=42 chars, >=1s
        lines: list[SubLine] = []
        cur_w, cur_start = [], None
        for w in words:
            if cur_start is None:
                cur_start = w.start
            cur_w.append(w.w)
            if len(" ".join(cur_w)) >= 42 or w.end - cur_start >= 3.0:
                lines.append(SubLine(text=" ".join(cur_w), start=cur_start, end=w.end, part=w.part))
                cur_w, cur_start = [], None
        if cur_w:
            lines.append(SubLine(text=" ".join(cur_w), start=cur_start or 0.0,
                                 end=words[-1].end, part=words[-1].part))

        subs = Subtitles(words=words, lines=lines)
        write_srt([l.model_dump() for l in lines], ctx.run_dir / "subtitles" / "subtitles.srt")

        result = AudioResult(episode_path=str(episode), duration_sec=round(duration, 2),
                             parts=[round(d, 2) for d in part_durations],
                             engine=engine, tts_provider=provider)
        return [("audio/speechplan.json", plan),
                ("subtitles/subtitles.json", subs),
                ("audio/audio_result.json", result)]
