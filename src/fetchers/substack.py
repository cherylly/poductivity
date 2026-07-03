"""Substack RSS fetcher."""

from __future__ import annotations

import logging
from datetime import datetime

import feedparser
import httpx
from bs4 import BeautifulSoup

from .base import BaseFetcher, FetchedEntry

logger = logging.getLogger(__name__)


class SubstackFetcher(BaseFetcher):
    """Fetches articles from Substack via RSS."""

    def supports(self, platform: str) -> bool:
        return platform == "substack"

    async def fetch_new_entries(
        self, source_url: str, since: datetime | None = None
    ) -> list[FetchedEntry]:
        rss_url = self._normalize_rss_url(source_url)
        logger.info(f"Fetching Substack RSS: {rss_url}")

        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            resp = await client.get(rss_url)
            resp.raise_for_status()

        feed = feedparser.parse(resp.text)
        entries = []

        for item in feed.entries:
            published = self._parse_date(item)
            if since and published and published <= since:
                continue

            raw_text = self._extract_text(item)
            entries.append(
                FetchedEntry(
                    title=item.get("title", "Untitled"),
                    url=item.get("link", ""),
                    published_at=published,
                    content_type="article",
                    raw_text=raw_text,
                )
            )

        logger.info(f"Found {len(entries)} new Substack entries")
        return entries

    def _normalize_rss_url(self, url: str) -> str:
        url = url.rstrip("/")
        if url.endswith("/feed"):
            return url
        return f"{url}/feed"

    def _parse_date(self, item) -> datetime | None:
        if hasattr(item, "published_parsed") and item.published_parsed:
            from time import mktime
            return datetime.fromtimestamp(mktime(item.published_parsed))
        return None

    def _extract_text(self, item) -> str:
        content = ""
        if "content" in item:
            content = item.content[0].get("value", "")
        elif "summary" in item:
            content = item.summary

        if content:
            soup = BeautifulSoup(content, "html.parser")
            return soup.get_text(separator="\n", strip=True)
        return ""
