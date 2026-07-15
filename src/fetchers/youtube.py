"""YouTube fetcher: RSS for video discovery + transcript API for subtitles."""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime

import feedparser
import httpx
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.proxies import GenericProxyConfig

from .base import BaseFetcher, FetchedEntry

logger = logging.getLogger(__name__)

YOUTUBE_RSS_TEMPLATE = "https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"


def _get_proxy_url():
    return os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy") or None


class YouTubeFetcher(BaseFetcher):
    """Fetches YouTube videos via RSS and retrieves transcripts."""

    def supports(self, platform: str) -> bool:
        return platform == "youtube"

    async def fetch_new_entries(
        self, source_url: str, since: datetime | None = None
    ) -> list[FetchedEntry]:
        rss_url = await self._resolve_rss_url(source_url)
        logger.info(f"Fetching YouTube RSS: {rss_url}")

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(rss_url)
            resp.raise_for_status()

        feed = feedparser.parse(resp.text)
        entries = []

        for item in feed.entries:
            published = self._parse_date(item)
            if since and published and published <= since:
                continue

            video_id = self._extract_video_id(item)
            video_url = f"https://www.youtube.com/watch?v={video_id}" if video_id else item.get("link", "")

            transcript_text = None
            if video_id:
                transcript_text = self._get_transcript(video_id)

            # Fallback: use RSS description if transcript unavailable
            if not transcript_text:
                description = item.get("summary", "") or item.get("description", "")
                if description and len(description) > 100:
                    transcript_text = f"[Video description]\n{description}"

            entries.append(
                FetchedEntry(
                    title=item.get("title", "Untitled"),
                    url=video_url,
                    published_at=published,
                    content_type="video",
                    raw_text=transcript_text,
                )
            )

        logger.info(f"Found {len(entries)} new YouTube entries")
        return entries

    async def _resolve_rss_url(self, url: str) -> str:
        """Convert various YouTube URL formats to RSS feed URL."""
        if "feeds/videos.xml" in url:
            return url

        channel_id = self._extract_channel_id(url)
        if channel_id:
            return YOUTUBE_RSS_TEMPLATE.format(channel_id=channel_id)

        # Try to resolve from channel page
        channel_id = await self._fetch_channel_id(url)
        if channel_id:
            return YOUTUBE_RSS_TEMPLATE.format(channel_id=channel_id)

        raise ValueError(f"Cannot resolve YouTube RSS URL from: {url}")

    def _extract_channel_id(self, url: str) -> str | None:
        match = re.search(r"channel/(UC[\w-]+)", url)
        if match:
            return match.group(1)

        match = re.search(r"channel_id=(UC[\w-]+)", url)
        if match:
            return match.group(1)
        return None

    async def _fetch_channel_id(self, url: str) -> str | None:
        """Fetch channel page and extract channel ID from meta tags."""
        try:
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                resp = await client.get(url)
                match = re.search(r'"channelId":"(UC[\w-]+)"', resp.text)
                if match:
                    return match.group(1)
                match = re.search(r'<meta itemprop="channelId" content="(UC[\w-]+)"', resp.text)
                if match:
                    return match.group(1)
        except Exception as e:
            logger.warning(f"Failed to fetch channel ID from {url}: {e}")
        return None

    def _extract_video_id(self, item) -> str | None:
        yt_id = item.get("yt_videoid")
        if yt_id:
            return yt_id
        link = item.get("link", "")
        match = re.search(r"[?&]v=([\w-]+)", link)
        return match.group(1) if match else None

    def _get_transcript(self, video_id: str) -> str | None:
        """Get transcript with timestamps formatted as text."""
        try:
            proxy_url = _get_proxy_url()
            if proxy_url:
                proxy_config = GenericProxyConfig(
                    http_url=proxy_url,
                    https_url=proxy_url,
                )
                api = YouTubeTranscriptApi(proxy_config=proxy_config)
            else:
                api = YouTubeTranscriptApi()

            transcript_list = api.list(video_id)

            # Prefer manual transcripts, fallback to auto-generated
            transcript = None
            try:
                transcript = transcript_list.find_manually_created_transcript(["en"])
            except Exception:
                try:
                    transcript = transcript_list.find_generated_transcript(["en"])
                except Exception:
                    pass

            if not transcript:
                return None

            segments = transcript.fetch()
            lines = []
            for seg in segments:
                start = seg.start if hasattr(seg, 'start') else seg.get("start", 0)
                text = seg.text if hasattr(seg, 'text') else seg.get("text", "")
                timestamp = self._format_timestamp(start)
                lines.append(f"[{timestamp}] {text}")

            return "\n".join(lines)
        except Exception as e:
            logger.warning(f"Failed to get transcript for {video_id}: {type(e).__name__}")
            return None

    def _format_timestamp(self, seconds: float) -> str:
        mins = int(seconds) // 60
        secs = int(seconds) % 60
        return f"{mins:02d}:{secs:02d}"

    def _parse_date(self, item) -> datetime | None:
        if hasattr(item, "published_parsed") and item.published_parsed:
            from time import mktime
            return datetime.fromtimestamp(mktime(item.published_parsed))
        return None
