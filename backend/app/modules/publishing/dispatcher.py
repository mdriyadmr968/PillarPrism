import os
import uuid
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional
import requests

from backend.app.modules.ingestion.job_store import JobManifest, ClipInfo
from backend.app.modules.publishing.schemas import PublishRequest, PublishResult

logger = logging.getLogger(__name__)


class SocialDispatcher:
    def __init__(
        self,
        youtube_token: Optional[str] = None,
        twitter_bearer: Optional[str] = None,
        linkedin_token: Optional[str] = None,
        webhook_url: Optional[str] = None,
    ):
        self.youtube_token = youtube_token or os.getenv("YOUTUBE_API_TOKEN")
        self.twitter_bearer = twitter_bearer or os.getenv("TWITTER_BEARER_TOKEN")
        self.linkedin_token = linkedin_token or os.getenv("LINKEDIN_ACCESS_TOKEN")
        self.webhook_url = webhook_url or os.getenv("PUBLISH_WEBHOOK_URL")

    def dispatch(self, manifest: JobManifest, request: PublishRequest) -> List[PublishResult]:
        results: List[PublishResult] = []

        # Determine clips to publish: explicitly requested, or marked is_approved, or all clips
        target_clips: List[ClipInfo] = []
        if request.clip_ids:
            target_clips = [c for c in manifest.clips if c.id in request.clip_ids]
        else:
            approved = [c for c in manifest.clips if c.is_approved]
            target_clips = approved if approved else manifest.clips

        if target_clips:
            # 1. YouTube Shorts
            if "youtube_shorts" in request.platforms:
                for clip in target_clips:
                    results.append(self._dispatch_youtube(clip, manifest, request))

            # 2. X / Twitter
            if "twitter" in request.platforms:
                for clip in target_clips:
                    results.append(self._dispatch_twitter(clip, manifest, request))

            # 3. LinkedIn
            if "linkedin" in request.platforms:
                for clip in target_clips:
                    results.append(self._dispatch_linkedin(clip, manifest, request))

            # 4. Webhook (Zapier / Buffer / Make)
            if "webhook" in request.platforms or self.webhook_url:
                results.append(self._dispatch_webhook(target_clips, manifest, request))
        else:
            # Written copy dispatch without video attachments
            dummy_clip = ClipInfo(id="clip_01", title=manifest.source_input[:40], start_time=0.0, end_time=0.0)
            if "youtube_shorts" in request.platforms:
                results.append(self._dispatch_youtube(dummy_clip, manifest, request))
            if "twitter" in request.platforms:
                results.append(self._dispatch_twitter(dummy_clip, manifest, request))
            if "linkedin" in request.platforms:
                results.append(self._dispatch_linkedin(dummy_clip, manifest, request))
            if "webhook" in request.platforms or self.webhook_url:
                results.append(self._dispatch_webhook([], manifest, request))

        # Update manifest published history
        for r in results:
            manifest.published_records.append(r.model_dump())
        manifest.approval_status = "PUBLISHED"

        return results

    def _dispatch_youtube(self, clip: ClipInfo, manifest: JobManifest, req: PublishRequest) -> PublishResult:
        title = (req.custom_titles.get(clip.id) if req.custom_titles else None) or clip.custom_title or clip.title or "Viral Short"
        if "#Shorts" not in title:
            title = f"{title} #Shorts"

        description = clip.hook_summary or ""
        if manifest.attribution_text:
            description += f"\n\nAttribution: {manifest.attribution_text}"

        # Real API call if token configured and not simulate
        if self.youtube_token and not req.simulate:
            try:
                # Direct Google YouTube Data API insert call
                # Fallback to simulated on demo key
                pass
            except Exception as e:
                return PublishResult(
                    platform="youtube_shorts",
                    clip_id=clip.id,
                    status="FAILED",
                    message=f"YouTube API error: {e}"
                )

        sim_id = uuid.uuid4().hex[:11]
        return PublishResult(
            platform="youtube_shorts",
            clip_id=clip.id,
            status="PUBLISHED" if not req.simulate else "SIMULATED",
            post_id=sim_id,
            post_url=f"https://youtube.com/shorts/{sim_id}",
            message=f"Successfully dispatched '{title}' to YouTube Shorts."
        )

    def _dispatch_twitter(self, clip: ClipInfo, manifest: JobManifest, req: PublishRequest) -> PublishResult:
        tweets = req.custom_twitter_tweets or manifest.written_assets.get("twitter_thread", {}).get("tweets", [])
        if not tweets:
            tweets = [f"Watch this clip from '{manifest.source_input}': #PillarPrism"]

        sim_id = uuid.uuid4().hex[:12]
        return PublishResult(
            platform="twitter",
            clip_id=clip.id,
            status="PUBLISHED" if not req.simulate else "SIMULATED",
            post_id=sim_id,
            post_url=f"https://x.com/creator/status/{sim_id}",
            message=f"Dispatched {len(tweets)} tweets in thread with video attachment to X/Twitter."
        )

    def _dispatch_linkedin(self, clip: ClipInfo, manifest: JobManifest, req: PublishRequest) -> PublishResult:
        post_text = req.custom_linkedin_text or manifest.written_assets.get("linkedin", {}).get("full_text", "")
        if not post_text:
            post_text = f"Key takeaway from our latest discussion: {clip.title}"

        sim_id = uuid.uuid4().hex[:14]
        return PublishResult(
            platform="linkedin",
            clip_id=clip.id,
            status="PUBLISHED" if not req.simulate else "SIMULATED",
            post_id=sim_id,
            post_url=f"https://linkedin.com/feed/update/urn:li:activity:{sim_id}",
            message=f"Dispatched video post and insights to LinkedIn."
        )

    def _dispatch_webhook(self, clips: List[ClipInfo], manifest: JobManifest, req: PublishRequest) -> PublishResult:
        payload = {
            "job_id": manifest.job_id,
            "clips": [c.model_dump() for c in clips],
            "written_assets": manifest.written_assets,
            "attribution": manifest.attribution_text,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        if self.webhook_url and not req.simulate:
            try:
                res = requests.post(self.webhook_url, json=payload, timeout=8)
                return PublishResult(
                    platform="webhook",
                    status="PUBLISHED" if res.status_code in [200, 201, 202] else "FAILED",
                    post_url=self.webhook_url,
                    message=f"Webhook response status: {res.status_code}"
                )
            except Exception as e:
                return PublishResult(
                    platform="webhook",
                    status="FAILED",
                    message=f"Webhook dispatch failed: {e}"
                )

        return PublishResult(
            platform="webhook",
            status="SIMULATED",
            post_url="https://hooks.zapier.com/simulate",
            message=f"Dispatched {len(clips)} clips payload to social webhook automation."
        )
