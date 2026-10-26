from pydantic import BaseModel, Field, model_validator


class Chapter(BaseModel):
    t: str = Field(pattern=r"^\d{2}:\d{2}(:\d{2})?$")
    label: str = Field(min_length=1)


class ThumbnailSpec(BaseModel):
    ref: str | None = None
    text_overlay: str = Field(min_length=1)
    asset: str | None = None


class YoutubeMeta(BaseModel):
    made_for_kids: bool = False
    synthetic_disclosure: bool = True


class Metadata(BaseModel):
    """Publish kit produced by M5 (techplan §5.5)."""

    title: str = Field(min_length=1, max_length=70)
    description: str = Field(min_length=1)
    tags: list[str] = []
    chapters: list[Chapter] = []
    thumbnail: ThumbnailSpec
    youtube: YoutubeMeta = YoutubeMeta()

    @model_validator(mode="after")
    def _chapters_ordered(self):
        for a, b in zip(self.chapters, self.chapters[1:]):
            if b.t < a.t:
                raise ValueError("chapters must be in ascending time order")
        return self
