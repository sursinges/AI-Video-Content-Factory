from typing import Literal

from pydantic import BaseModel, Field


class EpisodeManifest(BaseModel):
    """Pipeline input for one episode (techplan §5.0)."""

    run_id: str = Field(pattern=r"^[a-zA-Z0-9_-]+$")
    channel_id: str
    topic: str = Field(min_length=3)
    format: str = "sleep_history"
    # Free length: None means the script skeleton decides, downstream works
    # from actual audio timings. Nothing may assume a fixed duration.
    target_minutes: int | None = None
    language: str = "ru"
    reference_urls: list[str] = []
    # optional: owner's ready script text — M1 skips LLM and chunks this as-is
    own_script: str | None = None
    # optional: author's guidance / notes for the AI (accents, length, details)
    script_notes: str | None = None
    profile: str = "config/channel.profile.yaml"
    export_dir: str | None = None  # optional custom export directory for final video and assets
    overrides: dict = {}   # deep-merged into profile; supports provider_overrides {llm: id, ...}


