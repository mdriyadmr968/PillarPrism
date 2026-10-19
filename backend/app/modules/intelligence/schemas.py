from typing import List, Optional
from pydantic import BaseModel, Field


class ClipCandidate(BaseModel):
    title: str = Field(description="Punchy, attention-grabbing title for the vertical clip")
    start_time: float = Field(description="Start timecode in seconds")
    end_time: float = Field(description="End timecode in seconds (duration between 30 and 75 seconds)")
    hook_score: int = Field(description="Virality hook retention score from 1 to 100", ge=1, le=100)
    hook_summary: str = Field(description="Explanation of the opening 0-3s hook sentence")
    virality_reason: str = Field(description="Why this segment will perform well on TikTok/Reels/Shorts")


class LinkedInPost(BaseModel):
    hook: str = Field(description="Opening 1-2 sentence hook line")
    context: str = Field(description="Short background context or pain point")
    key_takeaways: List[str] = Field(description="3-4 bullet-point key insights or takeaways")
    discussion_prompt: str = Field(description="Engaging question inviting comments")
    hashtags: List[str] = Field(default_factory=list, description="3-5 relevant industry hashtags")
    full_text: str = Field(description="Complete ready-to-publish LinkedIn post formatted with line breaks")


class TwitterThread(BaseModel):
    hook_tweet: str = Field(description="Opening hook tweet that stops the scroll")
    tweets: List[str] = Field(description="List of 5 to 7 sequential tweets providing deep value")
    call_to_action: str = Field(description="Final CTA tweet encouraging retweets and follows")


class NewsletterSection(BaseModel):
    heading: str
    timestamp: str = ""
    content: str


class NewsletterSummary(BaseModel):
    title: str
    subtitle: str
    executive_summary: str
    sections: List[NewsletterSection] = Field(default_factory=list)
    actionable_takeaway: str
    full_markdown: str = Field(description="Complete ready-to-send markdown newsletter document")


class ContentSynthesisOutput(BaseModel):
    clips: List[ClipCandidate] = Field(description="Top 3 to 5 standalone viral clip segments")
    linkedin: LinkedInPost
    twitter_thread: TwitterThread
    newsletter: NewsletterSummary
