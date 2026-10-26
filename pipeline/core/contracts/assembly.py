from pydantic import BaseModel, Field


class AssemblyResult(BaseModel):
    """Output of M4 (techplan §5.4). video_path is None in mock mode."""

    video_path: str | None = None
    duration_sec: float = Field(ge=0)
    voice_lufs: float | None = None
    notes: str = ""
