from pydantic import BaseModel, Field


class TtsSegment(BaseModel):
    part: int = Field(ge=1)
    text_with_tags: str = Field(min_length=1)
    char_count: int = Field(ge=1)


class SpeechPlan(BaseModel):
    """TTS plan produced by M2 before synthesis (techplan §5.2)."""

    provider: str
    voice_id: str
    model: str
    segments: list[TtsSegment] = Field(min_length=1)


class Word(BaseModel):
    w: str
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    part: int = Field(ge=1)


class SubLine(BaseModel):
    text: str = Field(min_length=1)
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    part: int = Field(ge=1)


class Subtitles(BaseModel):
    """Word-level timings from STT + grouped subtitle lines (techplan §5.2)."""

    words: list[Word] = Field(min_length=1)
    lines: list[SubLine] = Field(min_length=1)


class AudioResult(BaseModel):
    """Summary of M2 outputs: assembled episode audio + timing provenance."""

    episode_path: str | None = None
    duration_sec: float = Field(ge=0)
    parts: list[float] = []          # duration per script part, sec
    engine: str = "fallback"          # whisper | fallback
    tts_provider: str = "mock"
