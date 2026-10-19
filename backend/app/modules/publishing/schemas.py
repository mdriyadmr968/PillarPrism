from datetime import datetime, timezone
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class PublishRequest(BaseModel):
    clip_ids: List[str] = Field(default_factory=list, description="IDs of clips to publish. If empty, publishes all approved clips.")
    platforms: List[str] = Field(default_factory=lambda: ["youtube_shorts", "twitter", "linkedin"], description="Target platforms")
    custom_linkedin_text: Optional[str] = None
    custom_twitter_tweets: Optional[List[str]] = None
    custom_titles: Optional[Dict[str, str]] = None
    simulate: bool = False


class PublishResult(BaseModel):
    platform: str
    clip_id: Optional[str] = None
    status: str = "PUBLISHED"  # "PUBLISHED" | "SIMULATED" | "FAILED"
    post_url: Optional[str] = None
    post_id: Optional[str] = None
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    message: str = ""
