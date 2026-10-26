from typing import Literal

from pydantic import BaseModel, Field, model_validator


class FactCheckClaim(BaseModel):
    text: str
    verdict: Literal["well-known", "flagged"]


class FactCheck(BaseModel):
    status: Literal["pass", "warnings"]
    claims: list[FactCheckClaim] = []


class ScriptChunk(BaseModel):
    part: int = Field(ge=1)
    role: Literal["intro", "body", "final"]
    form: int = Field(ge=1, le=8)
    text: str = Field(min_length=1)
    char_count: int = Field(ge=1)
    critic_pass: bool = True
    factcheck: FactCheck = FactCheck(status="pass")

    @model_validator(mode="after")
    def _char_count_matches(self):
        if self.char_count != len(self.text):
            raise ValueError(f"char_count {self.char_count} != len(text) {len(self.text)}")
        return self


class Skeleton(BaseModel):
    """M1 internal artifact (script/skeleton.json): the episode backbone from
    which chunks are generated (adapted from 'Скелет.md')."""

    description: str
    anchors: list[str] = Field(min_length=4)          # 10-16 recommended
    chunks_with_examples: list[int] = Field(min_length=0)
    forms: list[str] = Field(min_length=1)            # 8 chunk forms
    ideas: list[str] = Field(min_length=1)            # body ideas == body_parts_count
    forbidden_phrases: list[str] = []
    self_instructions: list[str] = []
    number_of_parts: int = Field(ge=1)
    body_parts_count: int = Field(ge=1)


class Script(BaseModel):
    """Output of module M1 (techplan §5.1)."""

    title_working: str
    hook_summary: str
    chunks: list[ScriptChunk] = Field(min_length=1)
    full_text_char_count: int = Field(ge=1)

    @model_validator(mode="after")
    def _full_count_matches(self):
        total = sum(c.char_count for c in self.chunks)
        if self.full_text_char_count != total:
            raise ValueError("full_text_char_count != sum of chunk char_counts")
        # chunk roles: first is intro, last is final, middle are body
        if self.chunks[0].role != "intro":
            raise ValueError("first chunk must be intro")
        if len(self.chunks) > 1 and self.chunks[-1].role != "final":
            raise ValueError("last chunk must be final")
        for c in self.chunks[1:-1]:
            if c.role != "body":
                raise ValueError("middle chunks must be body")
        return self
