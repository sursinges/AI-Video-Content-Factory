from typing import Literal

from pydantic import BaseModel, Field, model_validator


class WorldContext(BaseModel):
    """Era/light/palette constraints built by M3 (techplan §5.3)."""

    era: str
    palette: list[str] = Field(min_length=1)
    light: str
    forbidden: list[str] = []


class Scene(BaseModel):
    id: str = Field(pattern=r"^s\d+$")
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    text_ref: str
    prompt: str = Field(min_length=1)
    negative: str = ""
    seed: int = Field(ge=0)
    asset: str | None = None
    status: Literal["pending", "done"] = "pending"

    @model_validator(mode="after")
    def _order(self):
        if self.end <= self.start:
            raise ValueError("scene end must be after start")
        return self


class Scenes(BaseModel):
    """Timed scene plan; downstream (M4) works from these timings (techplan §5.3)."""

    scenes: list[Scene] = Field(min_length=1)

    @model_validator(mode="after")
    def _monotonic(self):
        for a, b in zip(self.scenes, self.scenes[1:]):
            if b.start < a.start:
                raise ValueError("scene starts must be non-decreasing")
        return self
