from typing import Optional
from pydantic import BaseModel, Field


class CCVideoCandidate(BaseModel):
    id: str
    title: str
    url: str
    author: str = "Unknown Creator"
    duration: float = 0.0
    duration_formatted: str = "00:00"
    source_platform: str = "youtube_cc"  # "youtube_cc" | "internet_archive"
    license_type: str = "Creative Commons (CC-BY)"
    attribution_text: str = ""
    thumbnail_url: Optional[str] = None
    description: Optional[str] = None
