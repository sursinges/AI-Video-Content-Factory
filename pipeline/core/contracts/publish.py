from typing import Literal

from pydantic import BaseModel, Field


class PublishAccount(BaseModel):
    """One own YouTube channel in the M6 pool. Secrets live in the OS
    keyring; the file stores only references (techplan §5.6)."""

    id: str = Field(min_length=1)
    label: str
    oauth_profile: str = Field(min_length=1)
    default: bool = False


class PublishResult(BaseModel):
    account_id: str = Field(min_length=1)
    # None while mock/unlisted-pending; real upload returns the YT video id.
    video_id: str | None = None
    visibility: Literal["unlisted", "public", "private"] = "unlisted"
    uploaded_at: str | None = None
    status: Literal["mock", "done", "failed"] = "mock"
