"""Base fetcher interface and common utilities."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


@dataclass
class FetchedEntry:
    """Represents a single content item fetched from a source."""

    title: str
    url: str
    published_at: datetime | None
    content_type: str  # article / video / podcast
    raw_text: str | None = None
    audio_url: str | None = None  # for podcasts


class BaseFetcher(ABC):
    """Abstract base class for content fetchers."""

    @abstractmethod
    async def fetch_new_entries(self, source_url: str, since: datetime | None = None) -> list[FetchedEntry]:
        """Fetch new entries from a source since the given timestamp."""
        ...

    @abstractmethod
    def supports(self, platform: str) -> bool:
        """Whether this fetcher supports the given platform."""
        ...
