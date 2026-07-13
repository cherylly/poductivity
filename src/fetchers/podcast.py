"""Podcast fetcher: search RSS via Podcast Index + download audio."""

from __future__ import annotations

import hashlib
import logging
import time
from datetime import datetime

import feedparser
import httpx

from src.config import settings

from .base import BaseFetcher, FetchedEntry

logger = logging.getLogger(__name__)

PODCAST_INDEX_BASE = "https://api.podcastindex.org/api/1.0"


class PodcastFetcher(BaseFetcher):
    """Fetches podcast episodes via RSS, with Podcast Index search support."""

    def supports(self, platform: str) -> bool:
        return platform == "podcast"

    async def fetch_new_entries(
        self, source_url: str, since: datetime | None = None
    ) -> list[FetchedEntry]:
        logger.info(f"Fetching podcast RSS: {source_url}")

        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            resp = await client.get(source_url)
            resp.raise_for_status()

        feed = feedparser.parse(resp.text)
        entries = []

        for item in feed.entries[:10]:  # limit to latest 10 episodes
            published = self._parse_date(item)
            if since and published and published <= since:
                continue

            audio_url = self._extract_audio_url(item)
            raw_text = self._extract_description(item)
            entries.append(
                FetchedEntry(
                    title=item.get("title", "Untitled"),
                    url=item.get("link", ""),
                    published_at=published,
                    content_type="podcast",
                    raw_text=raw_text,
                    audio_url=audio_url,
                )
            )

        logger.info(f"Found {len(entries)} new podcast entries")
        return entries

    def _extract_description(self, item) -> str | None:
        """Extract episode description/show notes as fallback text content."""
        from bs4 import BeautifulSoup

        content = ""
        if "content" in item and item.content:
            content = item.content[0].get("value", "")
        elif hasattr(item, "summary") and item.summary:
            content = item.summary
        elif hasattr(item, "description") and item.description:
            content = item.description

        if content:
            soup = BeautifulSoup(content, "html.parser")
            text = soup.get_text(separator="\n", strip=True)
            if len(text) > 50:
                return f"[Episode description]\n{text}"
        return None

    def _extract_audio_url(self, item) -> str | None:
        """Extract audio URL from RSS enclosure."""
        if hasattr(item, "enclosures") and item.enclosures:
            for enc in item.enclosures:
                if "audio" in enc.get("type", ""):
                    return enc.get("href") or enc.get("url")
        for link in item.get("links", []):
            if "audio" in link.get("type", ""):
                return link.get("href")
        return None

    def _parse_date(self, item) -> datetime | None:
        if hasattr(item, "published_parsed") and item.published_parsed:
            from time import mktime
            return datetime.fromtimestamp(mktime(item.published_parsed))
        return None

    @staticmethod
    async def search_podcast_rss(query: str) -> list[dict]:
        """Search for a podcast by name using Podcast Index API.

        Returns list of {name, rss_url, description}.
        """
        if not settings.podcast_index_key or not settings.podcast_index_secret:
            logger.warning("Podcast Index API credentials not configured")
            return []

        epoch_time = int(time.time())
        auth_hash = hashlib.sha1(
            f"{settings.podcast_index_key}{settings.podcast_index_secret}{epoch_time}".encode()
        ).hexdigest()

        headers = {
            "X-Auth-Date": str(epoch_time),
            "X-Auth-Key": settings.podcast_index_key,
            "Authorization": auth_hash,
            "User-Agent": "ContentDigest/1.0",
        }

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{PODCAST_INDEX_BASE}/search/byterm",
                params={"q": query},
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()

        results = []
        for feed in data.get("feeds", [])[:5]:
            results.append({
                "name": feed.get("title", ""),
                "rss_url": feed.get("url", ""),
                "description": feed.get("description", "")[:200],
            })
        return results
